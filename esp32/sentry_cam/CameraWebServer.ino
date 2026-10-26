#include <Arduino.h>
#include "esp_camera.h"
#include <WiFi.h>
#include "esp_wifi.h"

// ===========================
// Select camera model in board_config.h
// ===========================
#include "board_config.h"
#include "secrets.h"  // WIFI_SSID / WIFI_PASSWORD (gitignored; see secrets.example.h)

// ===========================
// Enter your WiFi credentials
// ===========================
const char *ssid = WIFI_SSID;
const char *password = WIFI_PASSWORD;

void startCameraServer();
void setupLedFlash();

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println();

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  // OV2640 only (hardware JPEG). A GC2145 or OV3660/OV5640 module cannot do this: the init fails with 0x105/0x106 or the sensor check below prints a warning; use esp32/tile_stream for a GC2145.
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_VGA;  // 640x480, the plan's interface
  config.grab_mode = CAMERA_GRAB_LATEST;  // always the newest frame, never a stale queued one
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 12;  // 10-12; lower number = better quality but bigger frames
  config.fb_count = 2;
  if (!psramFound()) {
    config.frame_size = FRAMESIZE_SVGA;
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
  }

#if defined(CAMERA_MODEL_ESP_EYE)
  pinMode(13, INPUT_PULLUP);
  pinMode(14, INPUT_PULLUP);
#endif

  // camera init
  // 2026-10-26: on this board init failed with 0x105 (camera not detected) on some boots, mostly the first one after a flash. Power-cycle the sensor
  // first (PWDN high 200 ms) and retry; with this 13 of 13 boots found it (esp32/experiments/ov2640_rate). Cause not proven.
#if defined(PWDN_GPIO_NUM) && PWDN_GPIO_NUM >= 0
  pinMode(PWDN_GPIO_NUM, OUTPUT); digitalWrite(PWDN_GPIO_NUM, HIGH); delay(200); digitalWrite(PWDN_GPIO_NUM, LOW); delay(100);
#endif
  esp_err_t err = esp_camera_init(&config);
  for (int k = 0; k < 4 && err != ESP_OK; k++) {
    Serial.printf("Camera init try %d failed (0x%x), retrying\n", k + 1, err);
    esp_camera_deinit();
    delay(500);
    err = esp_camera_init(&config);
  }
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x", err);
    return;
  }

  sensor_t *s = esp_camera_sensor_get();
  Serial.printf("SENSOR PID=0x%04x VER=0x%02x MIDH=0x%02x MIDL=0x%02x addr=0x%02x\n", s->id.PID, s->id.VER, s->id.MIDH, s->id.MIDL, s->slv_addr);
  // initial sensors are flipped vertically and colors are a bit saturated
  if (s->id.PID == OV3660_PID) {
    s->set_vflip(s, 1);        // flip it back
    s->set_brightness(s, 1);   // up the brightness just a bit
    s->set_saturation(s, -2);  // lower the saturation
  }
  if (s->id.PID != OV2640_PID) {
    Serial.printf("WARNING: sensor PID 0x%04x is not an OV2640 (0x26): hardware JPEG may be missing. A GC2145 (0x2145) needs esp32/tile_stream\n", s->id.PID);
  }
  s->set_framesize(s, config.frame_size);  // the web UI starts at VGA; the stock sketch dropped to QVGA here

#if defined(CAMERA_MODEL_M5STACK_WIDE) || defined(CAMERA_MODEL_M5STACK_ESP32CAM)
  s->set_vflip(s, 1);
  s->set_hmirror(s, 1);
#endif

#if defined(CAMERA_MODEL_ESP32S3_EYE)
  s->set_vflip(s, 1);
#endif

// Setup LED FLash if LED pin is defined in camera_pins.h
#if defined(LED_GPIO_NUM)
  setupLedFlash();
#endif

  // same radio settings as esp32/tile_stream (worked on the phone hotspot): channels 1-13, 20 MHz, no power save. The hotspot hands out a new IP each time: tools/record.py finds this board by itself (esp32_ip = "auto", port 81).
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  wifi_country_t country = {"VN", 1, 13, 20, WIFI_COUNTRY_POLICY_MANUAL};
  esp_wifi_set_country(&country);
  esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW_HT20);
  WiFi.begin(ssid, password);

  Serial.print("WiFi connecting");
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    if (millis() - t0 > 30000) {  // hotspot off or on 5 GHz: restart and try again rather than wait forever
      Serial.println("\nWiFi not connected after 30 s (is the hotspot on 2.4 GHz?); restarting");
      ESP.restart();
    }
  }
  Serial.println("");
  Serial.printf("WiFi connected ip=%s rssi=%d channel=%d\n", WiFi.localIP().toString().c_str(), WiFi.RSSI(), WiFi.channel());

  startCameraServer();

  Serial.printf("Camera Ready! Stream: http://%s:81/stream  (page: http://%s/)\n", WiFi.localIP().toString().c_str(), WiFi.localIP().toString().c_str());
}

void loop() {
  // Do nothing. Everything is done in another task by the web server
  delay(10000);
}
