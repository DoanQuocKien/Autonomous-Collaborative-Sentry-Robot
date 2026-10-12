"""XFeat (CVPR 2024, Potje et al.) sparse feature extraction + mutual nearest neighbour matching.

Vendored from https://github.com/verlab/accelerated_features (commit e92685f, Apache-2.0, see LICENSE and NOTICE.md) and trimmed to what perception/entrance.py needs.
Changes: relative imports, no tqdm / kornia / LighterGlue / dense matching, weights are loaded with weights_only=True and no print.
"""
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from .interpolator import InterpolateSparse2d
from .model import XFeatModel


class XFeat(nn.Module):
	"""Inference module: detectAndCompute(image) -> keypoints / scores / 64-d descriptors, match(desc1, desc2) -> mutual NN indices."""

	def __init__(self, weights, top_k=4096, detection_threshold=0.05, device=None):
		super().__init__()
		self.dev = torch.device(device or ('cuda' if torch.cuda.is_available() else 'cpu'))
		self.net = XFeatModel().to(self.dev).eval()
		self.top_k = top_k
		self.detection_threshold = detection_threshold
		self.net.load_state_dict(torch.load(str(weights), map_location=self.dev, weights_only=True))
		self.interpolator = InterpolateSparse2d('bicubic')

	@torch.inference_mode()
	def detectAndCompute(self, x, top_k = None, detection_threshold = None):
		"""
			Compute sparse keypoints & descriptors. Supports batched mode.

			input:
				x -> torch.Tensor(B, C, H, W): grayscale or rgb image
				top_k -> int: keep best k features
			return:
				List[Dict]: 
					'keypoints'    ->   torch.Tensor(N, 2): keypoints (x,y)
					'scores'       ->   torch.Tensor(N,): keypoint scores
					'descriptors'  ->   torch.Tensor(N, 64): local features
		"""
		if top_k is None: top_k = self.top_k
		if detection_threshold is None: detection_threshold = self.detection_threshold
		x, rh1, rw1 = self.preprocess_tensor(x)

		B, _, _H1, _W1 = x.shape
        
		M1, K1, H1 = self.net(x)
		M1 = F.normalize(M1, dim=1)

		#Convert logits to heatmap and extract kpts
		K1h = self.get_kpts_heatmap(K1)
		mkpts = self.NMS(K1h, threshold=detection_threshold, kernel_size=5)

		#Compute reliability scores
		_nearest = InterpolateSparse2d('nearest')
		_bilinear = InterpolateSparse2d('bilinear')
		scores = (_nearest(K1h, mkpts, _H1, _W1) * _bilinear(H1, mkpts, _H1, _W1)).squeeze(-1)
		scores[torch.all(mkpts == 0, dim=-1)] = -1

		#Select top-k features
		idxs = torch.argsort(-scores)
		mkpts_x  = torch.gather(mkpts[...,0], -1, idxs)[:, :top_k]
		mkpts_y  = torch.gather(mkpts[...,1], -1, idxs)[:, :top_k]
		mkpts = torch.cat([mkpts_x[...,None], mkpts_y[...,None]], dim=-1)
		scores = torch.gather(scores, -1, idxs)[:, :top_k]

		#Interpolate descriptors at kpts positions
		feats = self.interpolator(M1, mkpts, H = _H1, W = _W1)

		#L2-Normalize
		feats = F.normalize(feats, dim=-1)

		#Correct kpt scale
		mkpts = mkpts * torch.tensor([rw1,rh1], device=mkpts.device).view(1, 1, -1)

		valid = scores > 0
		return [  
				   {'keypoints': mkpts[b][valid[b]],
					'scores': scores[b][valid[b]],
					'descriptors': feats[b][valid[b]]} for b in range(B) 
			   ]

	def preprocess_tensor(self, x):
		""" Guarantee that image is divisible by 32 to avoid aliasing artifacts. """
		if isinstance(x, np.ndarray):
			if len(x.shape) == 3:
				x = torch.tensor(x).permute(2,0,1)[None]
			elif len(x.shape) == 2:
				x = torch.tensor(x[..., None]).permute(2,0,1)[None]
			else:
				raise RuntimeError('For numpy arrays, only (H,W) or (H,W,C) format is supported.')
		
		
		if len(x.shape) != 4:
			raise RuntimeError('Input tensor needs to be in (B,C,H,W) format')
	
		x = x.to(self.dev).float()

		H, W = x.shape[-2:]
		_H, _W = (H//32) * 32, (W//32) * 32
		rh, rw = H/_H, W/_W

		x = F.interpolate(x, (_H, _W), mode='bilinear', align_corners=False)
		return x, rh, rw

	def get_kpts_heatmap(self, kpts, softmax_temp = 1.0):
		scores = F.softmax(kpts*softmax_temp, 1)[:, :64]
		B, _, H, W = scores.shape
		heatmap = scores.permute(0, 2, 3, 1).reshape(B, H, W, 8, 8)
		heatmap = heatmap.permute(0, 1, 3, 2, 4).reshape(B, 1, H*8, W*8)
		return heatmap

	def NMS(self, x, threshold = 0.05, kernel_size = 5):
		B, _, H, W = x.shape
		pad=kernel_size//2
		local_max = nn.MaxPool2d(kernel_size=kernel_size, stride=1, padding=pad)(x)
		pos = (x == local_max) & (x > threshold)
		pos_batched = [k.nonzero()[..., 1:].flip(-1) for k in pos]

		pad_val = max([len(x) for x in pos_batched])
		pos = torch.zeros((B, pad_val, 2), dtype=torch.long, device=x.device)

		#Pad kpts and build (B, N, 2) tensor
		for b in range(len(pos_batched)):
			pos[b, :len(pos_batched[b]), :] = pos_batched[b]

		return pos

	@torch.inference_mode()
	def match(self, feats1, feats2, min_cossim = 0.82):

		cossim = feats1 @ feats2.t()
		cossim_t = feats2 @ feats1.t()
		
		_, match12 = cossim.max(dim=1)
		_, match21 = cossim_t.max(dim=1)

		idx0 = torch.arange(len(match12), device=match12.device)
		mutual = match21[match12] == idx0

		if min_cossim > 0:
			cossim, _ = cossim.max(dim=1)
			good = cossim > min_cossim
			idx0 = idx0[mutual & good]
			idx1 = match12[mutual & good]
		else:
			idx0 = idx0[mutual]
			idx1 = match12[mutual]

		return idx0, idx1

	def parse_input(self, x):
		if len(x.shape) == 3:
			x = x[None, ...]

		if isinstance(x, np.ndarray):
			x = torch.tensor(x).permute(0,3,1,2)/255

		return x
