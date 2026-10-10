// GC2145 (no hardware JPEG): capture YUV422, compress with Espressif esp_new_jpeg (dual-core), send the JPEG to the laptop over UDP.
// Packets: 16-byte header + up to 1400 bytes. Header (little endian): magic 'SC' u16, phase u8, flags u8, frame_id u32, esp_ms u32, pkt_idx u16, pkt_cnt u16
// esp_ms is taken when the frame is grabbed. The laptop announces itself with "HELO" (broadcast, once a second) and the ESP32 sends to whoever announced.
// The laptop answers each completed frame with "ACK " + frame_id u32 + esp_ms u32, so rtt = grab -> laptop has the whole frame -> ack back.
#include <WiFi.h>
#include <WiFiUdp.h>
#include "esp_wifi.h"
#include "esp_camera.h"
#include "esp_jpeg_enc.h"
#define CAMERA_MODEL_AI_THINKER
#include "camera_pins.h"
#include "secrets.h"  // WIFI_SSID, WIFI_PASSWORD

#ifndef WIFI_PROTO
#define WIFI_PROTO 0  // 0 = default b/g/n, 1 = 802.11b+g only (robust legacy rates), 2 = 802.11b only (DSSS)
#endif
static const int PORT = 5600;
static const int PAYLOAD = 1400;
static const size_t OUT_MAX = 100000;
// Tuning sweep, always as fast as possible. task: Espressif helper task on core 0 (dual-core encode); sub: 3 = 4:2:0, 2 = 4:2:2 chroma; fb: camera frame buffers
struct Phase { framesize_t size; bool task; int sub; int quality; int fb; int xclk; bool cam; bool enc; wifi_power_t tx; const char *name; bool dram; int grabMs; };  // grabMs: when not encoding, grab and discard one frame this often  // dram: camera frame buffer in internal RAM instead of PSRAM  // enc false = no JPEG encoding (resend the stored JPEG)  // xclk in MHz; cam false = camera off, resend the last JPEG (pure Wi-Fi baseline)
#ifndef VARIANT
#define VARIANT 1
#endif
// One resolution only, camera initialised once: does the stream stay healthy over time? VARIANT 0 = dual-core encode + 2 frame buffers, 1 = single task + 1 frame buffer
// Long run of the real use case: camera on + encoding + streaming, one phase for an hour
static const Phase PHASES[] = {
  {FRAMESIZE_VGA, true,  3, 60, 2, 20, true,  true,  WIFI_POWER_19_5dBm, "A VGA 640x480 dual-core encode, 2 buffers", false, 80},
};
static const int N_PHASES = 1;
static const uint32_t PHASE_MS = 3600000UL;

WiFiUDP udp;
IPAddress laptop;
bool haveLaptop = false;
camera_config_t cfg;
jpeg_enc_handle_t enc = NULL;
uint8_t *outBuf = NULL;

static bool camStart(const Phase &ph) {
  cfg.frame_size = ph.size;  // buffers are sized at init, so reinitialise per phase
  cfg.xclk_freq_hz = ph.xclk * 1000000;
  cfg.fb_location = ph.dram ? CAMERA_FB_IN_DRAM : CAMERA_FB_IN_PSRAM;
  WiFi.setTxPower(ph.tx);
  if (!ph.cam) {
    esp_camera_deinit();  // stops the camera clock
    if (enc) { jpeg_enc_close(enc); enc = NULL; }
    return true;
  }
  cfg.fb_count = ph.fb;
  cfg.grab_mode = ph.fb > 1 ? CAMERA_GRAB_LATEST : CAMERA_GRAB_WHEN_EMPTY;
  esp_camera_deinit();
  if (esp_camera_init(&cfg) != ESP_OK) return false;
  if (enc) { jpeg_enc_close(enc); enc = NULL; }
  for (int k = 0; k < 3; k++) { camera_fb_t *f = esp_camera_fb_get(); if (f) esp_camera_fb_return(f); }  // settle, and read the real size
  camera_fb_t *f = esp_camera_fb_get();
  if (!f) return false;
  jpeg_enc_config_t ec = DEFAULT_JPEG_ENC_CONFIG();
  ec.width = f->width; ec.height = f->height;
  ec.src_type = JPEG_PIXEL_FORMAT_YCbYCr;  // the camera's YUV422 is Y Cb Y Cr
  ec.subsampling = (jpeg_subsampling_t)ph.sub;
  ec.quality = ph.quality;
  ec.task_enable = ph.task; ec.hfm_task_core = 0; ec.hfm_task_priority = 13;  // helper task on core 0 (Wi-Fi core)
  esp_camera_fb_return(f);
  return jpeg_enc_open(&ec, &enc) == JPEG_ERR_OK;
}

void setup() {
  Serial.begin(115200);
  cfg = {};
  cfg.ledc_channel = LEDC_CHANNEL_0; cfg.ledc_timer = LEDC_TIMER_0;
  cfg.pin_d0 = Y2_GPIO_NUM; cfg.pin_d1 = Y3_GPIO_NUM; cfg.pin_d2 = Y4_GPIO_NUM; cfg.pin_d3 = Y5_GPIO_NUM;
  cfg.pin_d4 = Y6_GPIO_NUM; cfg.pin_d5 = Y7_GPIO_NUM; cfg.pin_d6 = Y8_GPIO_NUM; cfg.pin_d7 = Y9_GPIO_NUM;
  cfg.pin_xclk = XCLK_GPIO_NUM; cfg.pin_pclk = PCLK_GPIO_NUM; cfg.pin_vsync = VSYNC_GPIO_NUM; cfg.pin_href = HREF_GPIO_NUM;
  cfg.pin_sccb_sda = SIOD_GPIO_NUM; cfg.pin_sccb_scl = SIOC_GPIO_NUM; cfg.pin_pwdn = PWDN_GPIO_NUM; cfg.pin_reset = RESET_GPIO_NUM;
  cfg.xclk_freq_hz = 20000000;  // lowering it made grabbing slower (measured)
  cfg.pixel_format = PIXFORMAT_YUV422;
  cfg.fb_location = CAMERA_FB_IN_PSRAM;
  cfg.fb_count = 2;
  cfg.grab_mode = CAMERA_GRAB_LATEST;
  outBuf = (uint8_t *)ps_malloc(OUT_MAX);

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // power save adds tens of ms of latency
  // Link robustness (found online): Espressif recommends 20 MHz channels in crowded 2.4 GHz; and a country that allows channels 1-13,
  // so a phone hotspot on channel 12/13 is not restricted.
  wifi_country_t country = {"VN", 1, 13, 20, WIFI_COUNTRY_POLICY_MANUAL};
  esp_wifi_set_country(&country);
  esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW_HT20);
#if WIFI_PROTO == 1
  esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_11B | WIFI_PROTOCOL_11G);
#elif WIFI_PROTO == 2
  esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_11B);
#endif
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) delay(250);
  if (WiFi.status() != WL_CONNECTED) { Serial.println("JPG wifi failed (is the hotspot on 2.4 GHz?)"); return; }
  Serial.printf("JPG wifi ok ip=%s rssi=%d channel=%d\n", WiFi.localIP().toString().c_str(), WiFi.RSSI(), WiFi.channel());
  udp.begin(PORT + 1);  // HELO and acks come here
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) { delay(500); return; }
  static uint8_t phase = 0;
  static uint32_t frameId = 0, phaseStart = 0, lastSend = 0, lastReport = 0;
  static uint32_t frames = 0, sendFail = 0, acks = 0, rttSum = 0, rttMax = 0, encUs = 0, sendUs = 0, jpgBytes = 0, encFail = 0;
  static bool inited = false;
  if (!inited || millis() - phaseStart > PHASE_MS) {
    if (inited) phase = (phase + 1) % N_PHASES;
    if (!camStart(PHASES[phase])) { Serial.println("JPG camera/encoder init failed"); delay(2000); return; }
    inited = true; phaseStart = millis(); lastReport = phaseStart;
    frames = sendFail = acks = rttSum = rttMax = encUs = sendUs = jpgBytes = encFail = 0;
    Serial.printf("JPG phase %d %s\n", phase, PHASES[phase].name);
  }
  static int lastJl = 0;
  bool synth = !PHASES[phase].cam || !PHASES[phase].enc;
  static uint32_t lastGrab = 0;
  if (synth && PHASES[phase].cam && haveLaptop && lastJl > 0 && millis() - lastGrab >= (uint32_t)PHASES[phase].grabMs) {  // camera runs, frames are grabbed and thrown away
    lastGrab = millis();
    camera_fb_t *g = esp_camera_fb_get();
    if (g) esp_camera_fb_return(g);
  }
  if (synth && millis() - lastSend < 80) delay(1);
  if (haveLaptop) {
    camera_fb_t *fb = synth ? NULL : esp_camera_fb_get();
    if (fb || (synth && lastJl > 0 && millis() - lastSend >= 80)) {
      uint32_t espMs = millis(), t1 = micros();
      int jl = lastJl;
      jpeg_error_t je = JPEG_ERR_OK;
      if (fb) {
        je = jpeg_enc_process(enc, fb->buf, fb->len, outBuf, OUT_MAX, &jl);
        esp_camera_fb_return(fb);
        if (je == JPEG_ERR_OK) lastJl = jl;
      }
      uint32_t t2 = micros();
      if (je != JPEG_ERR_OK) { encFail++; } else {
        uint16_t cnt = (jl + PAYLOAD - 1) / PAYLOAD;
        for (uint16_t i = 0; i < cnt; i++) {
          size_t off = (size_t)i * PAYLOAD, n = min((size_t)PAYLOAD, (size_t)jl - off);
          uint8_t h[16] = {'S', 'C', phase, 0};
          memcpy(h + 4, &frameId, 4); memcpy(h + 8, &espMs, 4); memcpy(h + 12, &i, 2); memcpy(h + 14, &cnt, 2);
          bool ok = false;
          for (int tries = 0; tries < 3 && !ok; tries++) {  // lwip runs out of buffers when the radio stalls: a short retry, then drop the frame
            udp.beginPacket(laptop, PORT);
            udp.write(h, 16);
            udp.write(outBuf + off, n);
            ok = udp.endPacket() == 1;
            if (!ok) delay(2);
          }
          if (!ok) { sendFail++; break; }  // never build up delay: give up on this frame
        }
        encUs += t2 - t1; sendUs += micros() - t2; jpgBytes += jl;
        frameId++; frames++; lastSend = millis();
      }
    }
  } else {
    delay(5);  // wait for the laptop to announce itself
  }
  while (udp.parsePacket() > 0) {
    uint8_t a[12];
    IPAddress from = udp.remoteIP();
    int got = udp.read(a, 12);
    if (got >= 4 && memcmp(a, "HELO", 4) == 0) {
      if (!haveLaptop || from != laptop) Serial.printf("JPG laptop found at %s\n", from.toString().c_str());
      laptop = from; haveLaptop = true;
    } else if (got == 12 && memcmp(a, "ACK ", 4) == 0) {
      uint32_t ms;
      memcpy(&ms, a + 8, 4);
      uint32_t rtt = millis() - ms;
      acks++; rttSum += rtt;
      if (rtt > rttMax) rttMax = rtt;
    }
  }
  if (millis() - lastReport >= 2000) {
    float s = (millis() - lastReport) / 1000.0f;
    uint32_t f = frames ? frames : 1;
    Serial.printf("JPG %s: sent %.1f fps, jpeg %u B, encode %u ms, send %u ms, send-fail %u, enc-fail %u, acked %u, rtt avg %u max %u ms, rssi %d, heap %u largest %u min %u\n",
                  PHASES[phase].name, frames / s, jpgBytes / f, encUs / f / 1000, sendUs / f / 1000, sendFail, encFail, acks,
                  acks ? rttSum / acks : 0, rttMax, WiFi.RSSI(),
                  (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL), (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL), (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL));
    frames = sendFail = acks = rttSum = rttMax = encUs = sendUs = jpgBytes = encFail = 0;
    lastReport = millis();
  }
}
