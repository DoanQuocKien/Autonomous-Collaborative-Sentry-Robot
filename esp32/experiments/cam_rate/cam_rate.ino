// Raw Bayer VGA (see esp32/tile_stream for the setup trick): does less sensor blanking raise the frame rate at the same pixel clock? Wi-Fi off.
#include "esp_camera.h"
#define CAMERA_MODEL_AI_THINKER
#include "camera_pins.h"

static sensor_t *S;

static void trial(const char *name, int f8, int fa, int hb, int vb) {
  S->set_reg(S, 0xfe, 0xff, 0x00);
  if (f8 >= 0) S->set_reg(S, 0xf8, 0x3f, f8);
  if (fa >= 0) S->set_reg(S, 0xfa, 0xf0, fa << 4);
  if (hb >= 0) { S->set_reg(S, 0x05, 0xff, hb >> 8); S->set_reg(S, 0x06, 0xff, hb & 0xff); }
  if (vb >= 0) { S->set_reg(S, 0x07, 0xff, vb >> 8); S->set_reg(S, 0x08, 0xff, vb & 0xff); }
  delay(400);
  for (int k = 0; k < 3; k++) { camera_fb_t *f = esp_camera_fb_get(); if (f) esp_camera_fb_return(f); }
  uint32_t t0 = millis(), n = 0, nul = 0;
  while (millis() - t0 < 3000) { camera_fb_t *f = esp_camera_fb_get(); if (f) { n++; esp_camera_fb_return(f); } else nul++; }
  Serial.printf("BLANK %-30s f8=%d fa=0x%02x hb=%d vb=%d -> %.1f fps (%u null)\n", name, S->get_reg(S, 0xf8, 0x3f), S->get_reg(S, 0xfa, 0xff),
                (S->get_reg(S, 0x05, 0xff) << 8) | S->get_reg(S, 0x06, 0xff), (S->get_reg(S, 0x07, 0xff) << 8) | S->get_reg(S, 0x08, 0xff), n / 3.0f, (unsigned)nul);
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0; c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM; c.pin_d1 = Y3_GPIO_NUM; c.pin_d2 = Y4_GPIO_NUM; c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM; c.pin_d5 = Y7_GPIO_NUM; c.pin_d6 = Y8_GPIO_NUM; c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM; c.pin_pclk = PCLK_GPIO_NUM; c.pin_vsync = VSYNC_GPIO_NUM; c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM; c.pin_sccb_scl = SIOC_GPIO_NUM; c.pin_pwdn = PWDN_GPIO_NUM; c.pin_reset = RESET_GPIO_NUM;
  c.fb_location = CAMERA_FB_IN_PSRAM; c.fb_count = 2; c.grab_mode = CAMERA_GRAB_LATEST;
  c.pixel_format = PIXFORMAT_YUV422; c.frame_size = FRAMESIZE_HVGA; c.xclk_freq_hz = 10000000;  // <= 10 MHz: the driver packs 2 bytes per DMA word (standard mode) instead of 1 (high-speed mode)
  if (esp_camera_init(&c) != ESP_OK) { Serial.println("BLANK init failed"); return; }
  S = esp_camera_sensor_get();
  S->set_framesize(S, FRAMESIZE_VGA);
  S->set_reg(S, 0xfe, 0xff, 0x00);
  S->set_reg(S, 0x84, 0x1f, 0x17);
  trial("xclk10 divx4 7 (= old 3.5)", 7, 2, -1, -1);
  trial("xclk10 divx4 15 (= old 13 fps)", 15, 2, -1, 12);
  for (int d = 17; d <= 29; d += 2) { char nm[40]; snprintf(nm, sizeof nm, "xclk10 divx4 %d vb12", d); trial(nm, d, 2, -1, 12); }
  trial("xclk10 divx4 21 hb 160 vb12", 21, 2, 160, 12);
  trial("xclk10 divx4 21 hb 64 vb12", 21, 2, 64, 12);
  trial("xclk10 divx4 9 divide_by 1 vb12", 9, 1, 280, 12);
  trial("xclk10 divx4 11 divide_by 1 vb12", 11, 1, 280, 12);
  trial("xclk10 divx4 13 divide_by 1 vb12", 13, 1, 280, 12);
  Serial.println("BLANK done");
}

void loop() { delay(1000); }
