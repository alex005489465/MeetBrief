"""
NeMo Speaker Diarizer - 使用 NVIDIA NeMo Toolkit 進行說話者分離
"""
import os
import tempfile
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Optional


class NemoDiarizer:
    """使用 NeMo Toolkit 的說話者分離器"""

    def __init__(self):
        """初始化 NeMo Diarizer"""
        # 延遲載入 NeMo（避免 import 時間過長）
        self.model = None
        self._init_model()

    def _init_model(self):
        """初始化 NeMo 模型"""
        try:
            from nemo.collections.asr.models import ClusteringDiarizer

            # 建立 NeMo 配置
            # 使用預設的 diarization 配置
            self.model_config = self._get_diarizer_config()
            print("NeMo Diarizer 配置完成")

        except ImportError as e:
            print(f"NeMo 未安裝或安裝不完整: {e}")
            raise

    def _convert_to_mono_wav(self, input_path: str, output_path: str) -> bool:
        """
        將音檔轉換為 16kHz 單聲道 WAV

        Args:
            input_path: 輸入音檔路徑
            output_path: 輸出 WAV 路徑

        Returns:
            是否成功
        """
        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-ar", "16000",  # 16kHz
                "-ac", "1",      # 單聲道
                "-f", "wav",
                output_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"FFmpeg 轉換失敗: {result.stderr}")
                return False
            return True
        except Exception as e:
            print(f"音檔轉換失敗: {e}")
            return False

    def _get_diarizer_config(self) -> dict:
        """
        取得 NeMo Diarizer 配置

        Returns:
            配置字典
        """
        from omegaconf import OmegaConf
        import torch

        # PyTorch 2.9.1 + CUDA 12.8 支援 sm_120 (RTX 5050)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"NeMo Diarizer 使用設備: {device}")

        config = {
            "device": device,
            "num_workers": 0,  # 避免共享內存不足
            "sample_rate": 16000,
            "batch_size": 64,
            "verbose": True,
            "diarizer": {
                "manifest_filepath": None,
                "out_dir": None,
                "oracle_vad": False,
                "collar": 0.25,
                "ignore_overlap": True,

                # VAD 配置
                "vad": {
                    "model_path": "vad_multilingual_marblenet",
                    "external_vad_manifest": None,
                    "parameters": {
                        "window_length_in_sec": 0.15,
                        "shift_length_in_sec": 0.01,
                        "smoothing": "median",
                        "overlap": 0.5,
                        "onset": 0.5,
                        "offset": 0.3,
                        "min_duration_on": 0.1,
                        "min_duration_off": 0.1,
                        "pad_onset": 0.1,
                        "pad_offset": 0.0,
                    }
                },

                # Speaker Embedding 配置
                "speaker_embeddings": {
                    "model_path": "titanet_large",
                    "parameters": {
                        "window_length_in_sec": 1.5,
                        "shift_length_in_sec": 0.75,
                        "multiscale_weights": [1.0],
                        "save_embeddings": False,
                    }
                },

                # Clustering 配置
                "clustering": {
                    "parameters": {
                        "oracle_num_speakers": False,
                        "max_num_speakers": 8,
                        "enhanced_count_thres": 80,
                        "max_rp_threshold": 0.25,
                        "sparse_search_volume": 30,
                        "maj_vote_spk_count": False,
                    }
                }
            }
        }

        return OmegaConf.create(config)

    def diarize(self, filepath: str, num_speakers: Optional[int] = None) -> List[Dict]:
        """
        執行說話者分離

        Args:
            filepath: 音檔路徑
            num_speakers: 說話者數量（None 為自動偵測）

        Returns:
            說話者區段列表 [{"start": float, "end": float, "speaker": str}, ...]
        """
        from nemo.collections.asr.models import ClusteringDiarizer
        from omegaconf import OmegaConf
        import json

        # 建立臨時目錄
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # 轉換音檔為 16kHz 單聲道 WAV
            wav_path = tmpdir / "audio.wav"
            if not self._convert_to_mono_wav(filepath, str(wav_path)):
                raise RuntimeError("音檔轉換失敗")
            print(f"音檔已轉換為 16kHz 單聲道: {wav_path}")

            # 建立 manifest 檔案
            manifest_path = tmpdir / "manifest.json"
            manifest_entry = {
                "audio_filepath": str(wav_path),
                "offset": 0,
                "duration": None,
                "label": "infer",
                "text": "-",
                "num_speakers": num_speakers,
                "rttm_filepath": None,
                "uem_filepath": None
            }

            with open(manifest_path, "w") as f:
                json.dump(manifest_entry, f)
                f.write("\n")

            # 更新配置
            config = self.model_config.copy()
            config.diarizer.manifest_filepath = str(manifest_path)
            config.diarizer.out_dir = str(tmpdir)

            # 設定說話者數量
            if num_speakers is not None:
                config.diarizer.clustering.parameters.oracle_num_speakers = True
                config.diarizer.clustering.parameters.max_num_speakers = num_speakers

            # 建立 Diarizer
            diarizer = ClusteringDiarizer(cfg=config)

            # 設置 verbose 屬性（NeMo 2.x 需要手動設置，繞過屬性限制）
            object.__setattr__(diarizer, '_verbose', True)

            # 執行 diarization
            diarizer.diarize()

            # 讀取結果 (RTTM 格式)
            # 使用轉換後的 audio.wav 的檔名
            rttm_path = tmpdir / "pred_rttms" / "audio.rttm"

            speaker_segments = self._parse_rttm(rttm_path)

        return speaker_segments

    def _parse_rttm(self, rttm_path: Path) -> List[Dict]:
        """
        解析 RTTM 檔案

        RTTM 格式:
        SPEAKER <file> <channel> <start> <duration> <NA> <NA> <speaker> <NA> <NA>

        Args:
            rttm_path: RTTM 檔案路徑

        Returns:
            說話者區段列表
        """
        segments = []

        if not rttm_path.exists():
            print(f"RTTM 檔案不存在: {rttm_path}")
            return segments

        with open(rttm_path, "r") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 8 and parts[0] == "SPEAKER":
                    start = float(parts[3])
                    duration = float(parts[4])
                    speaker = parts[7]

                    segments.append({
                        "start": start,
                        "end": start + duration,
                        "speaker": speaker
                    })

        # 按開始時間排序
        segments.sort(key=lambda x: x["start"])

        # 統計說話者
        speakers = set(s["speaker"] for s in segments)
        print(f"偵測到 {len(speakers)} 個說話者: {speakers}")
        print(f"共 {len(segments)} 個區段")

        return segments
