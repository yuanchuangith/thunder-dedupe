#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
特征提取模块 - pHash感知哈希 + CLIP深度特征
"""
import os
import pickle
import math
from typing import List, Optional, Tuple, Union
from pathlib import Path

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None

from utils.logger import logger

PROJECT_ROOT = Path(__file__).resolve().parents[3]
HF_HOME_DIR = PROJECT_ROOT / ".hf-home"
HF_HUB_CACHE_DIR = HF_HOME_DIR / "hub"
os.environ.setdefault("HF_HOME", str(HF_HOME_DIR))
os.environ.setdefault("TRANSFORMERS_CACHE", str(HF_HUB_CACHE_DIR))

# 尝试导入可选依赖
try:
    import imagehash
    from PIL import Image
    HAS_IMAGEHASH = True
except ImportError:
    HAS_IMAGEHASH = False
    logger.warning("imagehash库未安装，pHash功能不可用")

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    logger.warning("torch库未安装，CLIP功能不可用")

try:
    from transformers import CLIPModel, CLIPProcessor
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False
    logger.warning("transformers库未安装，CLIP功能不可用")


class FeatureExtractor:
    """特征提取器"""

    _clip_model = None
    _clip_processor = None
    _clip_device = "cpu"
    _clip_dtype = None

    @classmethod
    def get_preferred_device(cls) -> str:
        """自动选择最合适的推理设备。"""
        if HAS_TORCH and torch.cuda.is_available():
            return "cuda"
        return "cpu"

    @classmethod
    def _resolve_clip_source(cls, model_name: str) -> Tuple[str, bool]:
        """Resolve the best available CLIP source, preferring the local cache."""
        model_path = Path(model_name)
        if model_path.exists():
            return str(model_path), True

        snapshots_dir = HF_HUB_CACHE_DIR / f"models--{model_name.replace('/', '--')}" / "snapshots"
        if not snapshots_dir.exists():
            return model_name, False

        snapshots = sorted(
            (path for path in snapshots_dir.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for snapshot in snapshots:
            if (snapshot / "config.json").exists():
                return str(snapshot), True

        return model_name, False

    @classmethod
    def init_clip(cls, model_name: str = "openai/clip-vit-base-patch32", device: Optional[str] = None):
        """
        初始化CLIP模型

        Args:
            model_name: CLIP模型名称
            device: 运行设备 (cpu/cuda)，为空时自动选择
        """
        if not HAS_TORCH or not HAS_TRANSFORMERS:
            logger.warning("CLIP依赖未安装，跳过初始化")
            return False

        try:
            target_device = device or cls.get_preferred_device()
            cls._clip_device = target_device
            cls._clip_dtype = torch.float16 if target_device == "cuda" else torch.float32
            clip_source, local_only = cls._resolve_clip_source(model_name)
            load_kwargs = {"local_files_only": True} if local_only else {"cache_dir": str(HF_HUB_CACHE_DIR)}

            cls._clip_model = CLIPModel.from_pretrained(clip_source, **load_kwargs)
            cls._clip_processor = CLIPProcessor.from_pretrained(clip_source, **load_kwargs)
            cls._clip_model.eval()

            if local_only:
                logger.info(f"CLIP model loaded from local cache: {clip_source}")

            if target_device == "cuda" and torch.cuda.is_available():
                cls._clip_model = cls._clip_model.to(target_device)
                cls._clip_model = cls._clip_model.to(dtype=cls._clip_dtype)
                logger.info(f"CLIP模型已加载到 GPU: {torch.cuda.get_device_name(0)}")
            else:
                cls._clip_device = "cpu"
                cls._clip_dtype = torch.float32
                logger.info("CLIP模型已加载到 CPU")

            return True

        except Exception as e:
            logger.error(f"CLIP模型加载失败: {e}")
            return False

    @classmethod
    def is_clip_available(cls) -> bool:
        """检查CLIP是否可用"""
        return HAS_TORCH and HAS_TRANSFORMERS and cls._clip_model is not None

    @staticmethod
    def extract_phash(frame: np.ndarray, hash_size: int = 16) -> Optional[str]:
        """
        计算单帧的感知哈希

        Args:
            frame: 帧图像 (RGB格式 numpy数组)
            hash_size: 哈希大小

        Returns:
            64位十六进制哈希字符串
        """
        if not HAS_IMAGEHASH:
            return None

        try:
            # 转换为PIL Image
            pil_image = Image.fromarray(frame)

            # 计算pHash
            hash_value = imagehash.phash(pil_image, hash_size=hash_size)

            return str(hash_value)

        except Exception as e:
            logger.warning(f"pHash计算失败: {e}")
            return None

    @staticmethod
    def extract_phash_batch(frames: List[np.ndarray], hash_size: int = 16) -> List[str]:
        """
        批量计算pHash

        Args:
            frames: 帧图像列表
            hash_size: 哈希大小

        Returns:
            哈希字符串列表
        """
        hashes = []
        for frame in frames:
            hash_val = FeatureExtractor.extract_phash(frame, hash_size)
            if hash_val:
                hashes.append(hash_val)
        return hashes

    @classmethod
    def extract_clip_features(cls, frames: List[np.ndarray]) -> Optional[np.ndarray]:
        """
        计算帧序列的CLIP特征

        Args:
            frames: 帧图像列表 (RGB格式)

        Returns:
            平均特征向量 (512维)
        """
        if not cls.is_clip_available():
            return None

        if not HAS_NUMPY:
            logger.warning("numpy库未安装，跳过CLIP特征提取")
            return None

        try:
            # 转换为PIL Image
            pil_images = [Image.fromarray(frame) for frame in frames]

            # 处理图像
            inputs = cls._clip_processor(images=pil_images, return_tensors="pt")

            # 移动到设备
            inputs = {k: v.to(cls._clip_device) for k, v in inputs.items()}
            if cls._clip_device == "cuda" and "pixel_values" in inputs:
                inputs["pixel_values"] = inputs["pixel_values"].to(dtype=cls._clip_dtype)

            # 获取图像特征
            with torch.inference_mode():
                if cls._clip_device == "cuda":
                    with torch.autocast(device_type="cuda", dtype=torch.float16):
                        image_features = cls._clip_model.get_image_features(**inputs)
                else:
                    image_features = cls._clip_model.get_image_features(**inputs)

            # 转换为numpy并计算平均
            features = image_features.cpu().numpy()

            # 归一化
            norms = np.linalg.norm(features, axis=1, keepdims=True)
            features = features / (norms + 1e-8)

            # 计算平均特征
            avg_feature = np.mean(features, axis=0)

            # 再次归一化
            avg_norm = np.linalg.norm(avg_feature)
            avg_feature = avg_feature / (avg_norm + 1e-8)

            return avg_feature.astype(np.float32)

        except Exception as e:
            logger.warning(f"CLIP特征提取失败: {e}")
            return None

    @staticmethod
    def serialize_features(phashes: List[str], clip_feature: Optional[np.ndarray]) -> bytes:
        """
        序列化特征向量

        Args:
            phashes: pHash列表
            clip_feature: CLIP特征向量

        Returns:
            序列化的bytes
        """
        data = {
            'phashes': phashes,
            'clip_feature': clip_feature
        }
        return pickle.dumps(data)

    @staticmethod
    def deserialize_features(data: bytes) -> Tuple[List[str], Optional[np.ndarray]]:
        """
        反序列化特征向量

        Args:
            data: 序列化的bytes

        Returns:
            (pHash列表, CLIP特征向量)
        """
        try:
            features = pickle.loads(data)
            return features.get('phashes', []), features.get('clip_feature')
        except Exception as e:
            logger.warning(f"特征反序列化失败: {e}")
            return [], None

    @staticmethod
    def compute_hamming_distance(hash1: str, hash2: str) -> int:
        """
        计算两个哈希的汉明距离

        Args:
            hash1: 第一个哈希字符串
            hash2: 第二个哈希字符串

        Returns:
            汉明距离
        """
        if not hash1 or not hash2:
            return max(len(hash1 or ""), len(hash2 or ""), 16) * 4

        # 确保长度相同
        if len(hash1) != len(hash2):
            return max(len(hash1), len(hash2)) * 4

        distance = 0
        for c1, c2 in zip(hash1, hash2):
            # 转换为二进制并比较
            b1 = int(c1, 16)
            b2 = int(c2, 16)
            distance += bin(b1 ^ b2).count('1')

        return distance

    @staticmethod
    def compute_phash_similarity(hash1: str, hash2: str) -> float:
        """
        计算两个pHash的相似度

        Args:
            hash1: 第一个哈希字符串
            hash2: 第二个哈希字符串

        Returns:
            相似度 (0-1)
        """
        if not hash1 or not hash2:
            return 0.0

        distance = FeatureExtractor.compute_hamming_distance(hash1, hash2)
        max_distance = max(len(hash1), len(hash2)) * 4
        if max_distance <= 0:
            return 0.0

        similarity = 1.0 - (distance / max_distance)
        if HAS_NUMPY:
            return float(np.clip(similarity, 0.0, 1.0))
        return max(0.0, min(1.0, float(similarity)))

    @staticmethod
    def compute_phash_similarity_batch(hashes1: List[str], hashes2: List[str]) -> float:
        """
        计算两组哈希的平均相似度

        Args:
            hashes1: 第一组哈希列表
            hashes2: 第二组哈希列表

        Returns:
            平均相似度 (0-1)
        """
        if not hashes1 or not hashes2:
            return 0.0

        similarities = []

        # 对每组哈希计算最佳匹配相似度
        for h1 in hashes1:
            max_sim = 0.0
            for h2 in hashes2:
                sim = FeatureExtractor.compute_phash_similarity(h1, h2)
                max_sim = max(max_sim, sim)
            similarities.append(max_sim)

        # 计算平均
        if HAS_NUMPY:
            return float(np.mean(similarities))
        return sum(similarities) / len(similarities)

    @staticmethod
    def compute_clip_similarity(feature1: np.ndarray, feature2: np.ndarray) -> float:
        """
        计算两个CLIP特征向量的余弦相似度

        Args:
            feature1: 第一个特征向量
            feature2: 第二个特征向量

        Returns:
            余弦相似度 (0-1)
        """
        if feature1 is None or feature2 is None:
            return 0.0

        if HAS_NUMPY:
            # 计算余弦相似度
            dot_product = np.dot(feature1, feature2)
            norm1 = np.linalg.norm(feature1)
            norm2 = np.linalg.norm(feature2)
        else:
            try:
                vector1 = list(feature1)
                vector2 = list(feature2)
            except TypeError:
                return 0.0

            if len(vector1) != len(vector2):
                return 0.0

            dot_product = sum(a * b for a, b in zip(vector1, vector2))
            norm1 = math.sqrt(sum(a * a for a in vector1))
            norm2 = math.sqrt(sum(b * b for b in vector2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = dot_product / (norm1 * norm2)

        # 确保在0-1范围内
        if HAS_NUMPY:
            return float(np.clip(similarity, 0.0, 1.0))
        return max(0.0, min(1.0, float(similarity)))


# 默认特征提取器实例
feature_extractor = FeatureExtractor()
