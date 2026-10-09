// GC2145 (no hardware JPEG) at 640x480 RAW Bayer (1 byte per pixel, set up by hand: see camera setup) by conditional replenishment: the camera is fixed, so most of each frame is unchanged.
// Every frame: score each 64x32 tile against what the laptop already has (sampled luma difference), JPEG-encode the changed tiles
// (biggest change first) until a time budget is spent, send them, and refresh a couple of the oldest tiles to repair packet loss.
// JPEG encode costs about 0.65 us/pixel on the ESP32, so the budget buys about a third of a VGA frame per captured frame.
//
// UDP packets, little endian: 'S' 'T' type u8 flags u8 frame_id u32 esp_ms u32 a u16 b u16, then payload
//   type 0 tile      a = tile index, payload = JPEG scan data (the constant JPEG header is sent separately)
//   type 1 header    a = header length, payload = the JPEG header every tile shares (resent once a second)
//   type 2 frame end a = tiles sent in this frame, b = tiles that were dirty (sent + skipped for lack of time)
//   (the laptop can also send "REFR" to port+1: the ESP32 then resends every tile, so a receiver that starts late gets a complete picture)
//   type 3 tile      like 0 but payload is a complete JPEG (header differed)
//   type 4 tiles     a = number of tiles, payload = repeated [tile index u16][length u16][JPEG scan data]: several tiles share one packet, because a UDP send costs
//                    about 3.5 ms whatever its size. The JPEG work runs on core 1 while core 0 captures, scores and sends.
// The laptop announces itself with "HELO" (broadcast, once a second); it answers a frame end with "ACK " + frame_id + esp_ms.
#include <WiFi.h>
#include <WiFiUdp.h>
#include "esp_wifi.h"
#include "esp_camera.h"
#include "esp_jpeg_enc.h"
#define CAMERA_MODEL_AI_THINKER
#include "camera_pins.h"
#include "secrets.h"  // WIFI_SSID, WIFI_PASSWORD

#ifndef MOTION_THR
#define MOTION_THR 16  // mean absolute luma difference (0-255) that marks a tile as changed; raise it if sensor noise keeps tiles dirty
#endif
#ifndef BUDGET_US
#define BUDGET_US 35000  // encode time per frame; about 66 ms is available at 15 fps
#endif
#ifndef MAIN_CORE
#define MAIN_CORE 1  // core for scoring/packing/sending; the camera and Wi-Fi stay on core 0
#endif
#ifndef PLANAR
#define PLANAR 1  // 1 = send the four Bayer colour planes of each tile as quadrants (the receiver must use --planar, its default)
#endif
#ifndef RAW_DIVX4
#define RAW_DIVX4 11
#endif
#ifndef RAW_DIVBY
#define RAW_DIVBY 1
#endif
#ifndef VBLANK
#define VBLANK 12
#endif
#ifndef REFRESH_PER_FRAME
#define REFRESH_PER_FRAME 2  // oldest tiles resent every frame: a lost UDP packet heals within NT / REFRESH frames
#endif

static const int PORT = 5600;
static const int W = 640, H = 480, TW = 64, TH = 32, TILES_X = W / TW, TILES_Y = H / TH, NT = TILES_X * TILES_Y;
static const int QUALITY = 60;  // raw Bayer is a fine mosaic; a low quality smears the colour information
enum { T_TILE = 0, T_HDR = 1, T_END = 2, T_FULL = 3, T_TILES = 4 };

WiFiUDP udp;
IPAddress laptop;
bool haveLaptop = false;
static uint8_t sig[NT][128];  // internal RAM: a fingerprint of every tile as the laptop last received it (8 rows x 16 bytes sampled)
uint8_t *tileBuf = NULL;  // internal RAM: one tile, copied row by row
uint8_t *outBuf = NULL;
uint8_t pkt[1500];
jpeg_enc_handle_t enc = NULL;
uint8_t hdr[900];
int hdrLen = 0;
uint32_t lastHdrMs = 0, frameId = 0;
uint32_t lastSentFrame[NT];

struct Cand { uint16_t score; uint16_t idx; };
static int byScoreDesc(const void *a, const void *b) { return (int)((const Cand *)b)->score - (int)((const Cand *)a)->score; }

static bool sendPkt(uint8_t type, uint32_t espMs, uint16_t a, uint16_t b, const uint8_t *data, int n) {
  if (n > 1450) return false;
  pkt[0] = 'S'; pkt[1] = 'T'; pkt[2] = type; pkt[3] = 0;
  memcpy(pkt + 4, &frameId, 4); memcpy(pkt + 8, &espMs, 4); memcpy(pkt + 12, &a, 2); memcpy(pkt + 14, &b, 2);
  if (n) memcpy(pkt + 16, data, n);
  for (int tries = 0; tries < 3; tries++) {  // lwip is out of buffers when the radio stalls: a short retry, then give up (the tile stays dirty and is retried next frame)
    udp.beginPacket(laptop, PORT);
    udp.write(pkt, 16 + n);
    if (udp.endPacket() == 1) return true;
    delay(2);
  }
  return false;
}

// Fingerprint of a tile: 8 rows (every 4th) x two 8-byte pieces (one cache line each, because the frame sits in slow external RAM). Raw Bayer: same colours every time.
static inline void sampleTile(const uint8_t *cur, int tx, int ty, uint8_t *out) {
  for (int r = 0; r < 8; r++) {
    const uint8_t *row = cur + (size_t)(ty * TH + r * 4) * W + tx * TW;
    memcpy(out + r * 16, row + 8, 8);
    memcpy(out + r * 16 + 8, row + 40, 8);
  }
}

// mean absolute difference between the tile now and its fingerprint (what the laptop has)
static uint16_t tileScore(const uint8_t *cur, int tx, int ty) {
  uint8_t now[128];
  sampleTile(cur, tx, ty, now);
  const uint8_t *old = sig[ty * TILES_X + tx];
  uint32_t sum = 0;
  for (int i = 0; i < 128; i++) { int d = (int)now[i] - (int)old[i]; sum += d < 0 ? -d : d; }
  return sum / 128;
}

static int jpegHeaderEnd(const uint8_t *j, int n) {  // index just after the SOS header, where the entropy-coded data starts
  for (int i = 2; i + 4 < n; i++) if (j[i] == 0xFF && j[i + 1] == 0xDA) return i + 2 + ((j[i + 2] << 8) | j[i + 3]);
  return -1;
}

static void copyTile(uint8_t *dst, const uint8_t *src, int tx, int ty) {
  for (int r = 0; r < TH; r++) {
    size_t o = (size_t)(ty * TH + r) * W + tx * TW;
#if PLANAR
    // Bayer tile -> four colour planes in the four quadrants (R, G1, G2, B each 32x16): smooth images compress cheaper than a fine mosaic
    const uint8_t *row = src + o;
    int pr = r >> 1, qy = r & 1;
    for (int c = 0; c < TW; c += 2) {
      dst[(size_t)(qy * 16 + pr) * TW + (c >> 1)] = row[c];
      dst[(size_t)(qy * 16 + pr) * TW + 32 + (c >> 1)] = row[c + 1];
    }
#else
    memcpy(dst + (size_t)r * TW, src + o, TW);
#endif
  }
}

// Encoder worker on core 1: jobs are tile pixels, results are JPEGs. Both live in fixed pools; the queues carry the pool slot number.
static const int MAXJ = 6;  // tiles per batch: small, so the time budget is respected finely
static uint8_t jobPix[MAXJ][TW * TH];
static struct { uint16_t len; uint8_t data[1500]; } jobRes[MAXJ];
static uint16_t jobTile[MAXJ];
static QueueHandle_t jobQ, resQ;
static void encoderTask(void *arg) {
  for (;;) {
    uint8_t j;
    xQueueReceive(jobQ, &j, portMAX_DELAY);
    int jl = 0;
    if (jpeg_enc_process(enc, jobPix[j], TW * TH, jobRes[j].data, sizeof jobRes[j].data, &jl) != JPEG_ERR_OK) jl = 0;
    jobRes[j].len = jl;
    xQueueSend(resQ, &j, portMAX_DELAY);
  }
}

static void initAll() {
  Serial.begin(115200);
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0; c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM; c.pin_d1 = Y3_GPIO_NUM; c.pin_d2 = Y4_GPIO_NUM; c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM; c.pin_d5 = Y7_GPIO_NUM; c.pin_d6 = Y8_GPIO_NUM; c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM; c.pin_pclk = PCLK_GPIO_NUM; c.pin_vsync = VSYNC_GPIO_NUM; c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM; c.pin_sccb_scl = SIOC_GPIO_NUM; c.pin_pwdn = PWDN_GPIO_NUM; c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = 10000000;  // <= 10 MHz makes the driver pack 2 bytes per DMA word instead of 1 (half the capture work); the sensor PLL restores the pixel rate
  // The driver knows only YUV422/RGB565 for this sensor and the ESP32 camera layer refuses RAW. It only counts bytes per frame, though:
  // 480x320 YUV422 = 307200 bytes = one 640x480 raw frame at 1 byte per pixel. So start as HVGA YUV422, then put the sensor itself into VGA raw output.
  c.pixel_format = PIXFORMAT_YUV422;
  c.frame_size = FRAMESIZE_HVGA;
  c.fb_location = CAMERA_FB_IN_PSRAM;
  c.fb_count = 2;
  c.grab_mode = CAMERA_GRAB_LATEST;
  if (esp_camera_init(&c) != ESP_OK) { Serial.println("TILE camera init failed"); return; }
  sensor_t *sen = esp_camera_sensor_get();
  sen->set_framesize(sen, FRAMESIZE_VGA);
  sen->set_reg(sen, 0xfe, 0xff, 0x00);      // register page 0
  sen->set_reg(sen, 0x84, 0x1f, 0x17);      // output format: raw Bayer
  sen->set_reg(sen, 0xf8, 0x3f, RAW_DIVX4); // sensor PLL multiplier
  sen->set_reg(sen, 0xfa, 0xf0, RAW_DIVBY << 4);  // sensor clock divide_by (the driver sets 2)
  sen->set_reg(sen, 0x07, 0xff, 0x00);      // vertical blanking 46 -> 12 lines
  sen->set_reg(sen, 0x08, 0xff, VBLANK);
  // measured (esp32/cam_rate, Wi-Fi off): xclk 10 MHz + divx4 11 + divide_by 1 + vblank 12 = 15.7 fps clean; divx4 13 drops frames
  tileBuf = (uint8_t *)heap_caps_malloc((size_t)TW * TH, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  outBuf = (uint8_t *)heap_caps_malloc(8000, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  if (!tileBuf || !outBuf) { Serial.println("TILE out of memory"); return; }
  memset(sig, 0, sizeof sig);
  jpeg_enc_config_t ec = DEFAULT_JPEG_ENC_CONFIG();
  ec.width = TW; ec.height = TH; ec.src_type = JPEG_PIXEL_FORMAT_GRAY; ec.subsampling = JPEG_SUBSAMPLE_GRAY; ec.quality = QUALITY;
  ec.task_enable = false;  // the Wi-Fi core stays free
  if (jpeg_enc_open(&ec, &enc) != JPEG_ERR_OK) { Serial.println("TILE encoder open failed"); return; }
  jobQ = xQueueCreate(MAXJ, sizeof(uint8_t));
  resQ = xQueueCreate(MAXJ, sizeof(uint8_t));
  xTaskCreatePinnedToCore(encoderTask, "enc", 8192, NULL, 3, NULL, 1);

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  wifi_country_t country = {"VN", 1, 13, 20, WIFI_COUNTRY_POLICY_MANUAL};
  esp_wifi_set_country(&country);
  esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW_HT20);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) delay(250);
  if (WiFi.status() != WL_CONNECTED) { Serial.println("TILE wifi failed (is the hotspot on 2.4 GHz?)"); return; }
  Serial.printf("TILE wifi ok ip=%s rssi=%d channel=%d\n", WiFi.localIP().toString().c_str(), WiFi.RSSI(), WiFi.channel());
  udp.begin(PORT + 1);  // HELO and acks come here
}

static void step() {
  static uint32_t lastReport = 0, frames = 0, tilesSent = 0, dirtySum = 0, skipped = 0, sendFail = 0, acks = 0, rttSum = 0, rttMax = 0, workUs = 0, oversize = 0, grabUs = 0, ivUs = 0, ivN = 0, scoreUs = 0, copyUs = 0, encUs = 0, sendUs = 0, tileN = 0;
  static uint32_t lastTs = 0;
  if (!enc || WiFi.status() != WL_CONNECTED) { delay(500); return; }

  while (udp.parsePacket() > 0) {
    uint8_t a[12];
    IPAddress from = udp.remoteIP();
    int got = udp.read(a, 12);
    if (got >= 4 && memcmp(a, "HELO", 4) == 0) {
      if (!haveLaptop || from != laptop) Serial.printf("TILE laptop found at %s\n", from.toString().c_str());
      laptop = from; haveLaptop = true;
    } else if (got >= 4 && memcmp(a, "REFR", 4) == 0) {  // a receiver just started: forget what it has, so every tile is sent again
      memset(sig, 0xFF, sizeof sig);
    } else if (got == 12 && memcmp(a, "ACK ", 4) == 0) {
      uint32_t ms;
      memcpy(&ms, a + 8, 4);
      uint32_t rtt = millis() - ms;
      acks++; rttSum += rtt;
      if (rtt > rttMax) rttMax = rtt;
    }
  }
  if (!haveLaptop) { delay(5); return; }

  uint32_t g0 = micros();
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) return;
  grabUs += micros() - g0;
  uint32_t ts = (uint32_t)(fb->timestamp.tv_sec * 1000000LL + fb->timestamp.tv_usec);  // when the sensor finished this frame
  if (lastTs) { ivUs += ts - lastTs; ivN++; }
  lastTs = ts;
  uint32_t espMs = millis(), t0 = micros();
  const uint8_t *cur = fb->buf;

  Cand cand[NT + REFRESH_PER_FRAME];
  int n = 0;
  uint32_t ts0 = micros();
  for (int i = 0; i < NT; i++) {
    uint16_t s = tileScore(cur, i % TILES_X, i / TILES_X);
    if (s >= MOTION_THR) cand[n++] = {s, (uint16_t)i};
  }
  int dirty = n;
  scoreUs += micros() - ts0;
  qsort(cand, n, sizeof(Cand), byScoreDesc);
  for (int k = 0; k < REFRESH_PER_FRAME; k++) {  // the oldest tiles that are not already queued
    int best = -1;
    for (int i = 0; i < NT; i++) {
      bool queued = false;
      for (int q = 0; q < n; q++) if (cand[q].idx == i) { queued = true; break; }
      if (!queued && (best < 0 || lastSentFrame[i] < lastSentFrame[best])) best = i;
    }
    if (best >= 0) cand[n++] = {0, (uint16_t)best};
  }

  if (hdrLen > 0 && millis() - lastHdrMs > 1000) { sendPkt(T_HDR, espMs, hdrLen, 0, hdr, hdrLen); lastHdrMs = millis(); }
  int sent = 0, qpos = 0;
  uint32_t b0 = micros();
  while (qpos < n && micros() - t0 < BUDGET_US) {
    int k = n - qpos < MAXJ ? n - qpos : MAXJ;
    for (int b = 0; b < k; b++) {  // hand a batch of tiles to the encoder on core 1
      int idx = cand[qpos + b].idx;
      jobTile[b] = idx;
      copyTile(jobPix[b], cur, idx % TILES_X, idx / TILES_X);
      uint8_t jb = b;
      xQueueSend(jobQ, &jb, portMAX_DELAY);
    }
    qpos += k;
    static uint8_t payload[1450];
    uint16_t inPkt[32];
    int nPkt = 0, off = 0;
    for (int b = 0; b <= k; b++) {  // pack the results as they arrive; the extra pass flushes the last packet
      uint8_t j = 0;
      bool have = false;
      if (b < k) {
        xQueueReceive(resQ, &j, portMAX_DELAY);
        have = jobRes[j].len > 0;
        if (have && hdrLen == 0) {
          int he = jpegHeaderEnd(jobRes[j].data, jobRes[j].len);
          if (he > 0 && he < (int)sizeof(hdr)) { memcpy(hdr, jobRes[j].data, he); hdrLen = he; sendPkt(T_HDR, espMs, hdrLen, 0, hdr, hdrLen); lastHdrMs = millis(); }
        }
        have = have && hdrLen > 0 && jobRes[j].len > hdrLen && memcmp(jobRes[j].data, hdr, hdrLen) == 0;
        if (!have) continue;
      }
      int dl = have ? jobRes[j].len - hdrLen : 0;
      if (nPkt > 0 && (!have || off + 4 + dl > (int)sizeof payload || nPkt >= 32)) {  // flush
        if (sendPkt(T_TILES, espMs, nPkt, 0, payload, off)) {
          for (int q = 0; q < nPkt; q++) { sampleTile(cur, inPkt[q] % TILES_X, inPkt[q] / TILES_X, sig[inPkt[q]]); lastSentFrame[inPkt[q]] = frameId; }
          sent += nPkt;
        } else sendFail++;  // not delivered: leave the fingerprints alone so these tiles are retried
        nPkt = 0; off = 0;
      }
      if (have) {
        if (4 + dl > (int)sizeof payload) { oversize++; continue; }
        uint16_t t = jobTile[j], l = dl;
        memcpy(payload + off, &t, 2); memcpy(payload + off + 2, &l, 2); memcpy(payload + off + 4, jobRes[j].data + hdrLen, dl);
        off += 4 + dl;
        inPkt[nPkt++] = t;
      }
    }
  }
  encUs += micros() - b0;
  esp_camera_fb_return(fb);
  sendPkt(T_END, espMs, sent, dirty, NULL, 0);
  workUs += micros() - t0;
  frames++; tilesSent += sent; dirtySum += dirty; skipped += (dirty > sent ? dirty - sent : 0);
  frameId++;

  if (millis() - lastReport >= 2000) {
    float s = (millis() - lastReport) / 1000.0f;
    uint32_t f = frames ? frames : 1;
    Serial.printf("TILE camera interval %u ms, wait in fb_get %u ms | %.1f fps, %u tiles/frame (%u dirty, %u skipped), work %u ms/frame [score %u us, encode+send %u us per frame], send-fail %u (oversize %u), acked %u, rtt avg %u max %u ms, rssi %d, heap %u\n",
                  ivN ? ivUs / ivN / 1000 : 0, grabUs / f / 1000, frames / s, tilesSent / f, dirtySum / f, skipped / f, workUs / f / 1000, scoreUs / f, encUs / f, sendFail, oversize, acks, acks ? rttSum / acks : 0, rttMax, WiFi.RSSI(),
                  (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
    frames = tilesSent = dirtySum = skipped = sendFail = acks = rttSum = rttMax = workUs = oversize = grabUs = ivUs = ivN = scoreUs = copyUs = encUs = sendUs = tileN = 0;
    lastReport = millis();
  }
}

// The camera interrupt (and the camera's frame-copy task) land on the core that initialises the camera. Measured with Wi-Fi connected: started on core 1 the raw
// capture drops to 8-11 fps, on core 0 (the Wi-Fi core) it holds 12-15 fps. So the camera and Wi-Fi are set up from a core-0 task, but the stream logic itself
// (scoring, packing, sending) runs on core 1 next to the encoder, so core 0 is left to the camera and the radio.
static void mainTask(void *arg) {
  for (;;) {
    step();
    vTaskDelay(1);  // let the idle task feed the watchdog
  }
}

static void initTask(void *arg) {
  initAll();
  xTaskCreatePinnedToCore(mainTask, "stream", 20480, NULL, 2, NULL, MAIN_CORE);
  vTaskDelete(NULL);
}

void setup() { xTaskCreatePinnedToCore(initTask, "init", 20480, NULL, 2, NULL, 0); }
void loop() { vTaskDelay(1000); }
