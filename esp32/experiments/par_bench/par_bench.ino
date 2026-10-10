// Can two encoders on two cores give VGA at 15 fps? One real VGA YUV422 frame is grabbed once, then encoded repeatedly (no Wi-Fi, no camera running).
// Cases: crop height (480 = full VGA, 320 = the top 320 rows only) x (1 encoder | 1 encoder + its helper task | 2 encoders, one per core).
#include "esp_camera.h"
#include "esp_jpeg_enc.h"
#define CAMERA_MODEL_AI_THINKER
#include "camera_pins.h"

static const int W = 640, H = 480, N = 24, QUALITY = 60;
static uint8_t *frame = NULL;
static volatile uint32_t doneUs[2];
static volatile int doneBytes[2];
static volatile bool finished[2];

struct Job { int core; int h; bool helper; int n; };

static void worker(void *arg) {
  Job *j = (Job *)arg;
  jpeg_enc_config_t ec = DEFAULT_JPEG_ENC_CONFIG();
  ec.width = W; ec.height = j->h; ec.src_type = JPEG_PIXEL_FORMAT_YCbYCr; ec.subsampling = JPEG_SUBSAMPLE_420; ec.quality = QUALITY;
  ec.task_enable = j->helper; ec.hfm_task_core = 0; ec.hfm_task_priority = 13;
  jpeg_enc_handle_t h = NULL;
  uint8_t *out = (uint8_t *)ps_malloc(120000);
  int bytes = 0;
  if (jpeg_enc_open(&ec, &h) == JPEG_ERR_OK && out) {
    uint32_t t0 = micros();
    for (int i = 0; i < j->n; i++) {
      int ol = 0;
      if (jpeg_enc_process(h, frame, W * j->h * 2, out, 120000, &ol) == JPEG_ERR_OK) bytes = ol;
      vTaskDelay(1);  // let the idle task feed the watchdog (core 0 reset otherwise)
    }
    doneUs[j->core] = micros() - t0;
    jpeg_enc_close(h);
  } else {
    doneUs[j->core] = 0;
  }
  doneBytes[j->core] = bytes;
  free(out);
  finished[j->core] = true;
  vTaskDelete(NULL);
}

static void runCase(const char *name, int h, bool helper, int encoders) {
  finished[0] = finished[1] = false;
  static Job jobs[2];
  uint32_t t0 = micros();
  for (int e = 0; e < encoders; e++) {
    jobs[e] = {e == 0 ? 1 : 0, h, helper, N};  // first encoder on core 1 (the Arduino core), second on core 0
    xTaskCreatePinnedToCore(worker, "enc", 32768, &jobs[e], 5, NULL, jobs[e].core);
  }
  while (!(finished[jobs[0].core] && (encoders < 2 || finished[jobs[1].core]))) delay(5);
  float secs = (micros() - t0) / 1e6f;
  float fps = (N * encoders) / secs;
  Serial.printf("PAR %-44s %d frame(s) in %.2f s = %.1f fps total | %d B/frame\n", name, N * encoders, secs, fps, (int)doneBytes[jobs[0].core]);
}

// Is the encoder limited by PSRAM speed? Encode the frame as independent horizontal strips; each strip is first copied into fast internal RAM,
// and the JPEG is written to internal RAM too. The full frame is "done" when all strips are.
static void runStrips(const char *name, int stripH, bool helper, bool internalCopy) {
  jpeg_enc_config_t ec = DEFAULT_JPEG_ENC_CONFIG();
  ec.width = W; ec.height = stripH; ec.src_type = JPEG_PIXEL_FORMAT_YCbYCr; ec.subsampling = JPEG_SUBSAMPLE_420; ec.quality = QUALITY;
  ec.task_enable = helper; ec.hfm_task_core = 0; ec.hfm_task_priority = 13;
  jpeg_enc_handle_t h = NULL;
  size_t inBytes = (size_t)W * stripH * 2;
  uint8_t *inBuf = internalCopy ? (uint8_t *)heap_caps_malloc(inBytes, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT) : NULL;
  uint8_t *out = (uint8_t *)heap_caps_malloc(40000, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  if ((internalCopy && !inBuf) || !out || jpeg_enc_open(&ec, &h) != JPEG_ERR_OK) { Serial.printf("PAR %s: setup failed\n", name); free(inBuf); free(out); return; }
  int strips = H / stripH, totalBytes = 0;
  uint32_t t0 = micros();
  for (int f = 0; f < 12; f++) {
    totalBytes = 0;
    for (int s = 0; s < strips; s++) {
      const uint8_t *src = frame + (size_t)s * inBytes;
      if (internalCopy) { memcpy(inBuf, src, inBytes); src = inBuf; }
      int ol = 0;
      if (jpeg_enc_process(h, src, inBytes, out, 40000, &ol) == JPEG_ERR_OK) totalBytes += ol;
    }
    vTaskDelay(1);
  }
  float secs = (micros() - t0) / 1e6f;
  Serial.printf("PAR %-44s %d strips of %d rows: %.1f fps full frame, %.0f ms/frame, %d B/frame\n", name, strips, stripH, 12 / secs, secs * 1000 / 12, totalBytes);
  jpeg_enc_close(h);
  free(inBuf); free(out);
}

// Tiles (a small rectangle of the frame, copied row by row into internal RAM, encoded as its own small JPEG). How much does each tile cost?
static void runTiles(const char *name, int tw, int th, bool helper) {
  jpeg_enc_config_t ec = DEFAULT_JPEG_ENC_CONFIG();
  ec.width = tw; ec.height = th; ec.src_type = JPEG_PIXEL_FORMAT_YCbYCr; ec.subsampling = JPEG_SUBSAMPLE_420; ec.quality = QUALITY;
  ec.task_enable = helper; ec.hfm_task_core = 0; ec.hfm_task_priority = 13;
  jpeg_enc_handle_t h = NULL;
  size_t inBytes = (size_t)tw * th * 2;
  uint8_t *inBuf = (uint8_t *)heap_caps_malloc(inBytes, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  uint8_t *out = (uint8_t *)heap_caps_malloc(30000, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  if (!inBuf || !out || jpeg_enc_open(&ec, &h) != JPEG_ERR_OK) { Serial.printf("PAR %s: setup failed\n", name); free(inBuf); free(out); return; }
  int tx = W / tw, ty = H / th, tiles = 0;
  long bytes = 0;
  uint32_t t0 = micros();
  for (int f = 0; f < 6; f++) {
    for (int j = 0; j < ty; j++) for (int i = 0; i < tx; i++) {
      for (int r = 0; r < th; r++) memcpy(inBuf + (size_t)r * tw * 2, frame + ((size_t)(j * th + r) * W + i * tw) * 2, (size_t)tw * 2);
      int ol = 0;
      if (jpeg_enc_process(h, inBuf, inBytes, out, 30000, &ol) == JPEG_ERR_OK) bytes += ol;
      tiles++;
    }
    vTaskDelay(1);
  }
  float us = (micros() - t0) / (float)tiles;
  Serial.printf("PAR %-34s tile %3dx%-3d: %5.2f ms per tile, %2d tiles/frame, full frame %4.0f ms, %ld B/tile\n", name, tw, th, us / 1000, tx * ty, us * tx * ty / 1000, bytes / tiles);
  jpeg_enc_close(h);
  free(inBuf); free(out);
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
  c.xclk_freq_hz = 20000000; c.pixel_format = PIXFORMAT_YUV422; c.frame_size = FRAMESIZE_VGA;
  c.fb_location = CAMERA_FB_IN_PSRAM; c.fb_count = 1; c.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  if (esp_camera_init(&c) != ESP_OK) { Serial.println("PAR camera init failed"); return; }
  frame = (uint8_t *)ps_malloc(W * H * 2);
  for (int k = 0; k < 4; k++) {
    camera_fb_t *f = esp_camera_fb_get();
    if (f) { if (k == 3 && f->len == (size_t)W * H * 2) memcpy(frame, f->buf, f->len); esp_camera_fb_return(f); }
  }
  esp_camera_deinit();  // from here on the camera is off: pure encoder timing
  Serial.printf("PAR frame captured, free internal heap %u\n", (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
  //runCase("640x480, 1 encoder", 480, false, 1);
  //runCase("640x480, 1 encoder + helper task", 480, true, 1);
  //runCase("640x480, 2 encoders (one per core)", 480, false, 2);
  //runCase("640x320 crop, 1 encoder", 320, false, 1);
  //runCase("640x320 crop, 1 encoder + helper task", 320, true, 1);
  //runCase("640x320 crop, 2 encoders (one per core)", 320, false, 2);
  runTiles("single task", 128, 48, false);
  runTiles("single task", 64, 48, false);
  runTiles("single task", 160, 80, false);
  runTiles("single task", 64, 32, false);
  runTiles("single task", 32, 32, false);
  runTiles("with helper task", 128, 48, true);
  runTiles("with helper task", 64, 48, true);
  Serial.println("PAR done");
}

void loop() { delay(1000); }
