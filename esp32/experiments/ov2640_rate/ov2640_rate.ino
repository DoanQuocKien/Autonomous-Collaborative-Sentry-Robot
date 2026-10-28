// OV2640 hardware JPEG: frame rate and frame size per resolution / quality / camera clock, then one JPEG of each resolution as a base64 line
// ("JPG <name> <len>" then "B64 ..."). No Wi-Fi: separates the camera from the radio. Run with tools/esp_serial.py-style reads at 115200.
#include "esp_camera.h"
#include "mbedtls/base64.h"
#define CAMERA_MODEL_AI_THINKER
#include "camera_pins.h"

static camera_config_t C;

// A sensor that was mid-transfer when the ESP32 reset can hold SDA low and answer nothing (init 0x105): clock SCL until SDA is released, then power-cycle it.
static void camera_prep() {
  pinMode(SIOD_GPIO_NUM, INPUT_PULLUP); pinMode(SIOC_GPIO_NUM, OUTPUT_OPEN_DRAIN); digitalWrite(SIOC_GPIO_NUM, HIGH);
  delay(5);
  int sda0 = digitalRead(SIOD_GPIO_NUM), pulses = 0;
  while (digitalRead(SIOD_GPIO_NUM) == LOW && pulses < 18) {
    digitalWrite(SIOC_GPIO_NUM, LOW); delayMicroseconds(10); digitalWrite(SIOC_GPIO_NUM, HIGH); delayMicroseconds(10); pulses++;
  }
  Serial.printf("OVR sda before clear=%d, pulses=%d, sda after=%d\n", sda0, pulses, digitalRead(SIOD_GPIO_NUM));
  pinMode(PWDN_GPIO_NUM, OUTPUT); digitalWrite(PWDN_GPIO_NUM, HIGH); delay(200); digitalWrite(PWDN_GPIO_NUM, LOW); delay(100);
}

static bool start(framesize_t fs, int q, int xclk) {
  sensor_t *s = esp_camera_sensor_get();           // resolution and quality change at run time: a deinit/init cycle between trials failed on this board
  s->set_framesize(s, fs); s->set_quality(s, q);
  delay(300);
  for (int k = 0; k < 3; k++) { camera_fb_t *f = esp_camera_fb_get(); if (f) esp_camera_fb_return(f); }
  return true;
}

static void trial(const char *name, framesize_t fs, int q, int xclk, bool dump) {
  if (!start(fs, q, xclk)) return;
  uint32_t t0 = millis(), n = 0, nul = 0, bytes = 0, mx = 0;
  while (millis() - t0 < 5000) {
    camera_fb_t *f = esp_camera_fb_get();
    if (f) { n++; bytes += f->len; if (f->len > mx) mx = f->len; esp_camera_fb_return(f); } else nul++;
  }
  Serial.printf("OVR %-22s q=%d xclk=%dMHz -> %.1f fps, %u B avg, %u B max (%u null)\n", name, q, xclk / 1000000, n / 5.0f, n ? bytes / n : 0, mx, (unsigned)nul);
  if (dump) {
    camera_fb_t *f = esp_camera_fb_get();
    if (!f) return;
    size_t ol = 0, cap = f->len * 4 / 3 + 8;
    unsigned char *out = (unsigned char *)malloc(cap);
    mbedtls_base64_encode(out, cap, &ol, f->buf, f->len);
    Serial.printf("JPG %s %u\n", name, (unsigned)f->len);
    Serial.print("B64 "); Serial.write(out, ol); Serial.println();
    free(out); esp_camera_fb_return(f);
  }
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  C = {};
  C.ledc_channel = LEDC_CHANNEL_0; C.ledc_timer = LEDC_TIMER_0;
  C.pin_d0 = Y2_GPIO_NUM; C.pin_d1 = Y3_GPIO_NUM; C.pin_d2 = Y4_GPIO_NUM; C.pin_d3 = Y5_GPIO_NUM;
  C.pin_d4 = Y6_GPIO_NUM; C.pin_d5 = Y7_GPIO_NUM; C.pin_d6 = Y8_GPIO_NUM; C.pin_d7 = Y9_GPIO_NUM;
  C.pin_xclk = XCLK_GPIO_NUM; C.pin_pclk = PCLK_GPIO_NUM; C.pin_vsync = VSYNC_GPIO_NUM; C.pin_href = HREF_GPIO_NUM;
  C.pin_sccb_sda = SIOD_GPIO_NUM; C.pin_sccb_scl = SIOC_GPIO_NUM; C.pin_pwdn = PWDN_GPIO_NUM; C.pin_reset = RESET_GPIO_NUM;
  C.fb_location = CAMERA_FB_IN_PSRAM; C.fb_count = 2; C.grab_mode = CAMERA_GRAB_LATEST;
  C.pixel_format = PIXFORMAT_JPEG;
  C.frame_size = FRAMESIZE_VGA; C.jpeg_quality = 12; C.xclk_freq_hz = 20000000;
  camera_prep();
  esp_err_t err = ESP_FAIL;
  for (int k = 0; k < 5 && err != ESP_OK; k++) {    // a loose ribbon shows up as init failing on some tries only
    err = esp_camera_init(&C);
    Serial.printf("OVR init try %d -> 0x%x\n", k + 1, err);
    if (err != ESP_OK) { esp_camera_deinit(); delay(500); }
  }
  if (err != ESP_OK) return;
  sensor_t *s = esp_camera_sensor_get();
  Serial.printf("OVR sensor PID=0x%04x VER=0x%02x psram=%d\n", s->id.PID, s->id.VER, psramFound());
  trial("VGA", FRAMESIZE_VGA, 12, 20000000, true);
  trial("VGA", FRAMESIZE_VGA, 20, 20000000, false);
  trial("QVGA", FRAMESIZE_QVGA, 12, 20000000, true);
  trial("SVGA", FRAMESIZE_SVGA, 12, 20000000, false);
  Serial.println("OVR done");
}

void loop() { delay(1000); }
