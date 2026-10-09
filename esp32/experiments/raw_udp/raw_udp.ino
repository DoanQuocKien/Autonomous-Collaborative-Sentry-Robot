// Sends raw frames to the laptop as UDP packets: 16-byte header + up to 1400 bytes of pixels.
// Header (little endian): magic 'SC' u16, phase u8, flags u8, frame_id u32, esp_ms u32, pkt_idx u16, pkt_cnt u16
// The laptop announces itself with "HELO" (broadcast, once a second); the ESP32 sends to whoever announced, so no IP is configured.
// The laptop answers each completed frame with "ACK " + frame_id u32 + esp_ms u32; the ESP32 turns that into a round trip time.
#include <WiFi.h>
#include <WiFiUdp.h>
#include "esp_camera.h"
#define CAMERA_MODEL_AI_THINKER
#include "camera_pins.h"
#include "secrets.h"  // WIFI_SSID, WIFI_PASSWORD

static const int PORT = 5600;
static const int PAYLOAD = 1400;
struct Phase { framesize_t size; int fps; const char *name; bool cam; };  // fps 0 = as fast as possible; cam false = dummy data, camera off (pure Wi-Fi capacity)
static const Phase PHASES[] = {{FRAMESIZE_QVGA, 10, "QVGA 10fps", true}, {FRAMESIZE_QVGA, 15, "QVGA 15fps", true}, {FRAMESIZE_QVGA, 0, "QVGA max", true}, {FRAMESIZE_QVGA, 0, "NOCAM max", false}};
static const int N_PHASES = 4;
static const size_t DUMMY_LEN = 153600;  // = one QVGA RGB565 frame
static const uint32_t PHASE_MS = 8000;

WiFiUDP udp;
IPAddress laptop;
bool haveLaptop = false;
uint8_t *dummy = NULL;
camera_config_t cfg;

static bool camStart(framesize_t size) {
  cfg.frame_size = size;  // RGB565 buffers are sized at init, so reinitialise per size
  esp_camera_deinit();
  return esp_camera_init(&cfg) == ESP_OK;
}

void setup() {
  Serial.begin(115200);
  cfg = {};
  cfg.ledc_channel = LEDC_CHANNEL_0; cfg.ledc_timer = LEDC_TIMER_0;
  cfg.pin_d0 = Y2_GPIO_NUM; cfg.pin_d1 = Y3_GPIO_NUM; cfg.pin_d2 = Y4_GPIO_NUM; cfg.pin_d3 = Y5_GPIO_NUM;
  cfg.pin_d4 = Y6_GPIO_NUM; cfg.pin_d5 = Y7_GPIO_NUM; cfg.pin_d6 = Y8_GPIO_NUM; cfg.pin_d7 = Y9_GPIO_NUM;
  cfg.pin_xclk = XCLK_GPIO_NUM; cfg.pin_pclk = PCLK_GPIO_NUM; cfg.pin_vsync = VSYNC_GPIO_NUM; cfg.pin_href = HREF_GPIO_NUM;
  cfg.pin_sccb_sda = SIOD_GPIO_NUM; cfg.pin_sccb_scl = SIOC_GPIO_NUM; cfg.pin_pwdn = PWDN_GPIO_NUM; cfg.pin_reset = RESET_GPIO_NUM;
  cfg.xclk_freq_hz = 20000000;
  cfg.pixel_format = PIXFORMAT_RGB565;
  cfg.fb_location = CAMERA_FB_IN_PSRAM;
  cfg.fb_count = 2;
  cfg.grab_mode = CAMERA_GRAB_LATEST;

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // power save adds tens of ms of latency
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) delay(250);
  if (WiFi.status() != WL_CONNECTED) { Serial.println("RAW wifi failed (is the hotspot on 2.4 GHz?)"); return; }
  Serial.printf("RAW wifi ok ip=%s rssi=%d\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  dummy = (uint8_t *)ps_malloc(DUMMY_LEN);
  for (size_t i = 0; i < DUMMY_LEN; i++) dummy[i] = i;
  udp.begin(PORT + 1);  // acks come back here
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) { delay(500); return; }
  static uint8_t phase = 0;
  static uint32_t frameId = 0, phaseStart = 0, lastSend = 0, lastReport = 0;
  static uint32_t sentFrames = 0, sendFail = 0, acks = 0, rttSum = 0, rttMax = 0, sendMsSum = 0;
  static bool inited = false;
  if (!inited || millis() - phaseStart > PHASE_MS) {
    if (inited) phase = (phase + 1) % N_PHASES;
    if (!PHASES[phase].cam) esp_camera_deinit();
    else if (!camStart(PHASES[phase].size)) { Serial.println("RAW camera init failed"); delay(2000); return; }
    inited = true; phaseStart = millis(); lastReport = phaseStart;
    sentFrames = sendFail = acks = rttSum = rttMax = sendMsSum = 0;
    Serial.printf("RAW phase %d %s\n", phase, PHASES[phase].name);
  }
  int period = PHASES[phase].fps ? 1000 / PHASES[phase].fps : 0;
  if (millis() - lastSend < (uint32_t)period) {
    delay(1);
  } else {
    camera_fb_t *fb = PHASES[phase].cam ? esp_camera_fb_get() : NULL;
    const uint8_t *buf = fb ? fb->buf : dummy;
    size_t len = fb ? fb->len : DUMMY_LEN;
    if (haveLaptop && (fb || !PHASES[phase].cam)) {
      uint32_t espMs = millis(), tSend = micros();
      uint16_t cnt = (len + PAYLOAD - 1) / PAYLOAD;
      for (uint16_t i = 0; i < cnt; i++) {
        size_t off = (size_t)i * PAYLOAD, n = min((size_t)PAYLOAD, len - off);
        uint8_t h[16] = {'S', 'C', phase, 0};
        memcpy(h + 4, &frameId, 4); memcpy(h + 8, &espMs, 4); memcpy(h + 12, &i, 2); memcpy(h + 14, &cnt, 2);
        bool ok = false;
        for (int tries = 0; tries < 20 && !ok; tries++) {  // lwip runs out of buffers when we outpace the radio: wait and retry
          udp.beginPacket(laptop, PORT);
          udp.write(h, 16);
          udp.write(buf + off, n);
          ok = udp.endPacket() == 1;
          if (!ok) delay(1);
        }
        if (!ok) sendFail++;
      }
      sendMsSum += (micros() - tSend) / 1000;
      if (fb) esp_camera_fb_return(fb);
      frameId++; sentFrames++; lastSend = millis();
    }
  }
  while (udp.parsePacket() > 0) {
    uint8_t a[12];
    IPAddress from = udp.remoteIP();
    int got = udp.read(a, 12);
    if (got >= 4 && memcmp(a, "HELO", 4) == 0) {
      if (!haveLaptop || from != laptop) Serial.printf("RAW laptop found at %s\n", from.toString().c_str());
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
    Serial.printf("RAW %s: sent %.1f fps, send %u ms/frame, send-fail %u pkts, acked %u frames, rtt avg %u max %u ms, rssi %d\n",
                  PHASES[phase].name, sentFrames / s, sentFrames ? sendMsSum / sentFrames : 0, sendFail, acks, acks ? rttSum / acks : 0, rttMax, WiFi.RSSI());
    sentFrames = sendFail = acks = rttSum = rttMax = sendMsSum = 0;
    lastReport = millis();
  }
}
