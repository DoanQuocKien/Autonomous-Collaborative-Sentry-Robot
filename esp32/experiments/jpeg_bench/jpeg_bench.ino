// Software-JPEG speed test for sensors without hardware JPEG (GC2145). No Wi-Fi.
// For each combination of pixel format / frame size / camera clock: grab N frames, compress each with frame2jpg, print fps.
#include "esp_camera.h"
#include "esp_jpeg_enc.h"  // Espressif esp_new_jpeg (prebuilt library, lib/esp_new_jpeg)
#define CAMERA_MODEL_AI_THINKER
#include "camera_pins.h"

struct Combo { pixformat_t fmt; framesize_t size; int xclkMHz; const char *name; };
static const Combo COMBOS[] = {
  {PIXFORMAT_RGB565,   FRAMESIZE_QVGA, 20, "RGB565 320x240 xclk20"},
  {PIXFORMAT_YUV422,   FRAMESIZE_QVGA, 20, "YUV422 320x240 xclk20"},
  {PIXFORMAT_GRAYSCALE, FRAMESIZE_QVGA, 20, "GRAY   320x240 xclk20"},
  {PIXFORMAT_RGB565,   FRAMESIZE_QVGA, 10, "RGB565 320x240 xclk10"},
  {PIXFORMAT_GRAYSCALE, FRAMESIZE_QVGA, 10, "GRAY   320x240 xclk10"},
  {PIXFORMAT_GRAYSCALE, FRAMESIZE_CIF,  20, "GRAY   400x296 xclk20"},
  {PIXFORMAT_GRAYSCALE, FRAMESIZE_VGA,  20, "GRAY   640x480 xclk20"},
  {PIXFORMAT_YUV422,   FRAMESIZE_VGA,  20, "YUV422 640x480 xclk20"},
};
static const int QUALITY = 60;  // frame2jpg: 0-100, higher = better picture, bigger file
static const int N = 30;

static jpeg_pixel_format_t jpegType(pixformat_t f) {
  return f == PIXFORMAT_GRAYSCALE ? JPEG_PIXEL_FORMAT_GRAY : f == PIXFORMAT_YUV422 ? JPEG_PIXEL_FORMAT_YCbYCr : JPEG_PIXEL_FORMAT_RGB565_BE;
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
  c.fb_location = CAMERA_FB_IN_PSRAM;
  c.fb_count = 2;
  c.grab_mode = CAMERA_GRAB_LATEST;
  for (unsigned i = 0; i < sizeof(COMBOS) / sizeof(COMBOS[0]); i++) {
    c.pixel_format = COMBOS[i].fmt;  // buffers are sized at init, so reinitialise for every combination
    c.frame_size = COMBOS[i].size;
    c.xclk_freq_hz = COMBOS[i].xclkMHz * 1000000;
    esp_camera_deinit();
    esp_err_t err = esp_camera_init(&c);
    if (err != ESP_OK) { Serial.printf("BENCH %s: init failed 0x%x\n", COMBOS[i].name, err); continue; }
    for (int k = 0; k < 3; k++) { camera_fb_t *f = esp_camera_fb_get(); if (f) esp_camera_fb_return(f); }  // settle
    uint32_t tGrab = 0, tEnc = 0, bytes = 0, raw = 0; int ok = 0;
    uint32_t tEsp = 0, bytesEsp = 0; int okEsp = 0;
    jpeg_enc_handle_t eh = NULL;
    uint8_t *outBuf = (uint8_t *)ps_malloc(200000);
    uint32_t t0 = millis();
    for (int k = 0; k < N; k++) {
      uint32_t a = micros();
      camera_fb_t *f = esp_camera_fb_get();
      uint32_t b = micros();
      if (!f) continue;
      uint8_t *jpg = NULL; size_t len = 0;
      bool good = frame2jpg(f, QUALITY, &jpg, &len);
      uint32_t d = micros();
      raw = f->len;
      if (!eh) {  // open the Espressif encoder on the first frame (needs the real width and height)
        jpeg_enc_config_t ec = DEFAULT_JPEG_ENC_CONFIG();
        ec.width = f->width; ec.height = f->height; ec.src_type = jpegType(COMBOS[i].fmt);
        ec.subsampling = COMBOS[i].fmt == PIXFORMAT_GRAYSCALE ? JPEG_SUBSAMPLE_GRAY : JPEG_SUBSAMPLE_420;
        ec.quality = QUALITY;
        ec.task_enable = true; ec.hfm_task_core = 0; ec.hfm_task_priority = 13;  // DUAL: second core helps encode
        if (jpeg_enc_open(&ec, &eh) != JPEG_ERR_OK) eh = NULL;
      }
      if (eh) {
        int outLen = 0;
        uint32_t e0 = micros();
        jpeg_error_t je = jpeg_enc_process(eh, f->buf, f->len, outBuf, 200000, &outLen);
        if (je == JPEG_ERR_OK) { okEsp++; tEsp += micros() - e0; bytesEsp += outLen; }
      }
      esp_camera_fb_return(f);
      if (good) { ok++; bytes += len; tGrab += b - a; tEnc += d - b; free(jpg); }
    }
    float secs = (millis() - t0) / 1000.0f;
    if (eh) jpeg_enc_close(eh);
    free(outBuf);
    Serial.printf("BENCH %s: esp_new_jpeg %d/%d ok, jpeg %.0f ms -> %u B\n", COMBOS[i].name, okEsp, N, okEsp ? tEsp / 1000.0f / okEsp : 0, okEsp ? bytesEsp / okEsp : 0);
    Serial.printf("BENCH %s: frame2jpg %d/%d ok, %.1f fps | grab %.0f ms, jpeg %.0f ms, raw %u B -> %u B\n", COMBOS[i].name, ok, N,
                  ok / secs, ok ? tGrab / 1000.0f / ok : 0, ok ? tEnc / 1000.0f / ok : 0, raw, ok ? bytes / ok : 0);
  }
  Serial.println("BENCH done");
}

void loop() { delay(1000); }
