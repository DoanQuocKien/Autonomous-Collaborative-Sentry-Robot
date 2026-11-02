import numpy as np

from third_party.bytetrack.basetrack import BaseTrack, TrackState
from third_party.bytetrack.kalman_filter import KalmanFilter
from third_party.bytetrack.matching import fuse_score, iou_distance, linear_assignment


class STrack(BaseTrack):
    shared_kalman = KalmanFilter()

    def __init__(self, tlwh, score, cls=0, idx=0):
        # wait activate
        self._tlwh = np.asarray(tlwh, dtype=np.float32)
        self.kalman_filter = None
        self.mean = None
        self.covariance = None
        self.is_activated = False

        self.score = float(score)
        self.cls = int(cls)
        self.idx = int(idx)
        self.tracklet_len = 0

    def predict(self):
        mean_state = self.mean.copy()
        if self.state != TrackState.Tracked:
            mean_state[7] = 0
        self.mean, self.covariance = self.kalman_filter.predict(
            mean_state, self.covariance
        )

    @staticmethod
    def multi_predict(stracks):
        if len(stracks) > 0:
            multi_mean = np.asarray([st.mean.copy() for st in stracks])
            multi_covariance = np.asarray([st.covariance for st in stracks])
            for i, st in enumerate(stracks):
                if st.state != TrackState.Tracked:
                    multi_mean[i][7] = 0
            multi_mean, multi_covariance = STrack.shared_kalman.multi_predict(
                multi_mean, multi_covariance
            )
            for i, (mean, cov) in enumerate(zip(multi_mean, multi_covariance)):
                stracks[i].mean = mean
                stracks[i].covariance = cov

    def activate(self, kalman_filter, frame_id):
        """Start a new tracklet."""
        self.kalman_filter = kalman_filter
        self.track_id = self.next_id()
        self.mean, self.covariance = self.kalman_filter.initiate(
            self.tlwh_to_xyah(self._tlwh)
        )

        self.tracklet_len = 0
        self.state = TrackState.Tracked
        if frame_id == 1:
            self.is_activated = True
        self.frame_id = frame_id
        self.start_frame = frame_id

    def re_activate(self, new_track, frame_id, new_id=False):
        self.mean, self.covariance = self.kalman_filter.update(
            self.mean, self.covariance, self.tlwh_to_xyah(new_track.tlwh)
        )
        self.tracklet_len = 0
        self.state = TrackState.Tracked
        self.is_activated = True
        self.frame_id = frame_id
        if new_id:
            self.track_id = self.next_id()
        self.score = new_track.score
        self.cls = new_track.cls
        self.idx = new_track.idx

    def update(self, new_track, frame_id):
        """Update a matched track."""
        self.frame_id = frame_id
        self.tracklet_len += 1

        new_tlwh = new_track.tlwh
        self.mean, self.covariance = self.kalman_filter.update(
            self.mean, self.covariance, self.tlwh_to_xyah(new_tlwh)
        )
        self.state = TrackState.Tracked
        self.is_activated = True

        self.score = new_track.score
        self.cls = new_track.cls
        self.idx = new_track.idx

    @property
    def tlwh(self):
        """Get current position in bounding box format `(top left x, top left y, width, height)`."""
        if self.mean is None:
            return self._tlwh.copy()
        ret = self.mean[:4].copy()
        ret[2] *= ret[3]
        ret[:2] -= ret[2:] / 2
        return ret

    @property
    def tlbr(self):
        """Convert bounding box to format `(min x, min y, max x, max y)`."""
        ret = self.tlwh.copy()
        ret[2:] += ret[:2]
        return ret

    @staticmethod
    def tlwh_to_xyah(tlwh):
        """Convert bounding box to format `(center x, center y, aspect ratio, height)`."""
        ret = np.asarray(tlwh).copy()
        ret[:2] += ret[2:] / 2
        ret[2] /= ret[3]
        return ret

    @staticmethod
    def tlbr_to_tlwh(tlbr):
        ret = np.asarray(tlbr).copy()
        ret[2:] -= ret[:2]
        return ret


def joint_stracks(tlista, tlistb):
    exists = {}
    res = []
    for t in tlista:
        exists[t.track_id] = 1
        res.append(t)
    for t in tlistb:
        tid = t.track_id
        if not exists.get(tid, 0):
            exists[tid] = 1
            res.append(t)
    return res


def sub_stracks(tlista, tlistb):
    stracks = {}
    for t in tlista:
        stracks[t.track_id] = t
    for t in tlistb:
        tid = t.track_id
        if stracks.get(tid, 0):
            del stracks[tid]
    return list(stracks.values())


def remove_duplicate_stracks(stracksa, stracksb):
    pdist = iou_distance(stracksa, stracksb)
    pairs = np.where(pdist < 0.15)
    dupa, dupb = list(), list()
    for p, q in zip(*pairs):
        timep = stracksa[p].frame_id - stracksa[p].start_frame
        timeq = stracksb[q].frame_id - stracksb[q].start_frame
        if timep > timeq:
            dupb.append(q)
        else:
            dupa.append(p)
    resa = [t for i, t in enumerate(stracksa) if not i in dupa]
    resb = [t for i, t in enumerate(stracksb) if not i in dupb]
    return resa, resb


class BYTETracker(object):
    def __init__(self, args, frame_rate=30):
        # Supports args as dict or SimpleNamespace
        cfg = args if isinstance(args, dict) else vars(args)
        self.track_high_thresh = float(cfg.get("track_high_thresh", cfg.get("track_thresh", 0.25)))
        self.track_low_thresh = float(cfg.get("track_low_thresh", 0.1))
        self.new_track_thresh = float(cfg.get("new_track_thresh", self.track_high_thresh))
        self.match_thresh = float(cfg.get("match_thresh", 0.8))
        self.track_buffer = int(cfg.get("track_buffer", 30))
        self.fuse_score = bool(cfg.get("fuse_score", False))

        self.frame_id = 0
        self.max_time_lost = int(frame_rate / 30.0 * self.track_buffer)
        self.kalman_filter = KalmanFilter()

        self.tracked_stracks = []  # type: list[STrack]
        self.lost_stracks = []  # type: list[STrack]
        self.removed_stracks = []  # type: list[STrack]

    def reset(self):
        self.frame_id = 0
        self.tracked_stracks = []
        self.lost_stracks = []
        self.removed_stracks = []
        BaseTrack.reset_counter()

    def update(self, output_results, img_info=None, img_size=None):
        """Update tracker with detections and advance frame.

        `output_results` can be:
        - ndarray or list of rows: [x1, y1, x2, y2, score, (optional class), ...]
        - Ultralytics Boxes object with .data attribute
        """
        self.frame_id += 1
        activated_stracks = []
        refind_stracks = []
        lost_stracks = []
        removed_stracks = []

        if hasattr(output_results, "data"):
            data = output_results.data
            if hasattr(data, "cpu"):
                data = data.cpu().numpy()
            output_results = np.asarray(data, dtype=np.float32)
        elif not isinstance(output_results, np.ndarray):
            output_results = np.asarray(output_results, dtype=np.float32)

        if output_results.size == 0 or len(output_results.shape) != 2:
            scores = np.empty((0,), dtype=np.float32)
            bboxes = np.empty((0, 4), dtype=np.float32)
            classes = np.empty((0,), dtype=int)
            indices = np.empty((0,), dtype=int)
        else:
            bboxes = output_results[:, :4]
            scores = output_results[:, 4]
            classes = output_results[:, 5].astype(int) if output_results.shape[1] > 5 else np.zeros(len(scores), dtype=int)
            indices = np.arange(len(scores), dtype=int)

        remain_inds = scores >= self.track_high_thresh
        inds_low = scores >= self.track_low_thresh
        inds_high = scores < self.track_high_thresh
        inds_second = np.logical_and(inds_low, inds_high)

        dets_second = bboxes[inds_second]
        dets = bboxes[remain_inds]
        scores_keep = scores[remain_inds]
        scores_second = scores[inds_second]
        cls_keep = classes[remain_inds]
        cls_second = classes[inds_second]
        idx_keep = indices[remain_inds]
        idx_second = indices[inds_second]

        if len(dets) > 0:
            detections = [
                STrack(STrack.tlbr_to_tlwh(tlbr), s, c, idx)
                for (tlbr, s, c, idx) in zip(dets, scores_keep, cls_keep, idx_keep)
            ]
        else:
            detections = []

        unconfirmed = []
        tracked_stracks = []
        for track in self.tracked_stracks:
            if not track.is_activated:
                unconfirmed.append(track)
            else:
                tracked_stracks.append(track)

        # Step 2: First association, with high score detections
        strack_pool = joint_stracks(tracked_stracks, self.lost_stracks)
        STrack.multi_predict(strack_pool)
        dists = iou_distance(strack_pool, detections)
        if self.fuse_score:
            dists = fuse_score(dists, detections)
        matches, u_track, u_detection = linear_assignment(dists, thresh=self.match_thresh)

        for itracked, idet in matches:
            track = strack_pool[itracked]
            det = detections[idet]
            if track.state == TrackState.Tracked:
                track.update(detections[idet], self.frame_id)
                activated_stracks.append(track)
            else:
                track.re_activate(det, self.frame_id, new_id=False)
                refind_stracks.append(track)

        # Step 3: Second association, with low score detections
        if len(dets_second) > 0:
            detections_second = [
                STrack(STrack.tlbr_to_tlwh(tlbr), s, c, idx)
                for (tlbr, s, c, idx) in zip(dets_second, scores_second, cls_second, idx_second)
            ]
        else:
            detections_second = []

        r_tracked_stracks = [
            strack_pool[i]
            for i in u_track
            if strack_pool[i].state == TrackState.Tracked
        ]
        dists = iou_distance(r_tracked_stracks, detections_second)
        matches, u_track, u_detection_second = linear_assignment(dists, thresh=0.5)
        for itracked, idet in matches:
            track = r_tracked_stracks[itracked]
            det = detections_second[idet]
            if track.state == TrackState.Tracked:
                track.update(det, self.frame_id)
                activated_stracks.append(track)
            else:
                track.re_activate(det, self.frame_id, new_id=False)
                refind_stracks.append(track)

        for it in u_track:
            track = r_tracked_stracks[it]
            if not track.state == TrackState.Lost:
                track.mark_lost()
                lost_stracks.append(track)

        # Deal with unconfirmed tracks, usually tracks with only one beginning frame
        detections = [detections[i] for i in u_detection]
        dists = iou_distance(unconfirmed, detections)
        if self.fuse_score:
            dists = fuse_score(dists, detections)
        matches, u_unconfirmed, u_detection = linear_assignment(dists, thresh=0.7)
        for itracked, idet in matches:
            unconfirmed[itracked].update(detections[idet], self.frame_id)
            activated_stracks.append(unconfirmed[itracked])
        for it in u_unconfirmed:
            track = unconfirmed[it]
            track.mark_removed()
            removed_stracks.append(track)

        # Step 4: Init new stracks
        for inew in u_detection:
            track = detections[inew]
            if track.score < self.new_track_thresh:
                continue
            track.activate(self.kalman_filter, self.frame_id)
            activated_stracks.append(track)

        # Step 5: Update state
        for track in self.lost_stracks:
            if self.frame_id - track.end_frame > self.max_time_lost:
                track.mark_removed()
                removed_stracks.append(track)

        self.tracked_stracks = [
            t for t in self.tracked_stracks if t.state == TrackState.Tracked
        ]
        self.tracked_stracks = joint_stracks(self.tracked_stracks, activated_stracks)
        self.tracked_stracks = joint_stracks(self.tracked_stracks, refind_stracks)
        self.lost_stracks = sub_stracks(self.lost_stracks, self.tracked_stracks)
        self.lost_stracks.extend(lost_stracks)
        self.lost_stracks = sub_stracks(self.lost_stracks, self.removed_stracks)
        self.removed_stracks.extend(removed_stracks)
        self.tracked_stracks, self.lost_stracks = remove_duplicate_stracks(
            self.tracked_stracks, self.lost_stracks
        )

        # Return observed output formatted as [x1, y1, x2, y2, track_id, score, cls, idx]
        output_stracks = [track for track in self.tracked_stracks if track.is_activated]
        res = []
        for track in output_stracks:
            tlbr = track.tlbr
            res.append([
                float(tlbr[0]),
                float(tlbr[1]),
                float(tlbr[2]),
                float(tlbr[3]),
                int(track.track_id),
                float(track.score),
                int(track.cls),
                int(track.idx),
            ])
        if len(res) == 0:
            return np.empty((0, 8), dtype=np.float32)
        return np.asarray(res, dtype=np.float32)
