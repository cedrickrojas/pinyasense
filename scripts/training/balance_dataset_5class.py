#!/usr/bin/env python3
"""
Create a balanced 5-class YOLO dataset with an exact target count per class.

Default behavior:
- Input: imported_dataset/yolov8_detection
- Output: imported_dataset/yolov8_detection_5class_1k
- Classes: Heart Rot, Fruit Rot, Yellow Spot, Pink Disease, Healthy
- Target: 1000 images per class

This script remaps the original 7 classes to 5 system classes and uses image
augmentation (flip/brightness/noise/blur) when oversampling is needed.
"""

from __future__ import annotations

import argparse
import random
import shutil
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import yaml


TARGET_CLASS_NAMES = [
    "Heart Rot",
    "Fruit Rot",
    "Yellow Spot",
    "Pink Disease",
    "Healthy",
]


@dataclass
class Sample:
    image_path: Path
    label_path: Path
    labels: list[list[float]]
    mapped_primary: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Balance YOLO dataset into 5 classes with fixed image count"
    )
    parser.add_argument(
        "--input",
        default="imported_dataset/yolov8_detection",
        help="Input YOLO dataset root",
    )
    parser.add_argument(
        "--output",
        default="imported_dataset/yolov8_detection_5class_1k",
        help="Output YOLO dataset root",
    )
    parser.add_argument(
        "--target-per-class",
        type=int,
        default=1000,
        help="Exact number of images per class",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    return parser.parse_args()


def load_data_yaml(dataset_root: Path) -> dict:
    yaml_path = dataset_root / "data_linux.yaml"
    if not yaml_path.exists():
        yaml_path = dataset_root / "data.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError("Could not find data_linux.yaml or data.yaml")
    with yaml_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_name(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def build_class_map(original_names: list[str]) -> dict[int, int]:
    """
    Map 7 dataset classes into 5 system classes.

    Mapping used:
    - Crown_Rot_Disease -> Heart Rot
    - Fruit_Fasciation_Disorder -> Fruit Rot
    - Fruit_Rot_Disease -> Fruit Rot
    - Mealybug_Wilt_Disease -> Yellow Spot
    - Multiple_Crown_Disorder -> Pink Disease
    - No_Disease -> Healthy
    - Root_Rot_Disease -> Heart Rot
    """
    canonical = {
        "crown_rot_disease": 0,
        "fruit_fasciation_disorder": 1,
        "fruit_rot_disease": 1,
        "mealybug_wilt_disease": 2,
        "multiple_crown_disorder": 3,
        "no_disease": 4,
        "root_rot_disease": 0,
    }
    class_map: dict[int, int] = {}
    for idx, name in enumerate(original_names):
        key = normalize_name(name)
        if key not in canonical:
            raise ValueError(f"Unknown class in dataset: {name}")
        class_map[idx] = canonical[key]
    return class_map


def parse_label_file(label_path: Path) -> list[list[float]]:
    rows: list[list[float]] = []
    if not label_path.exists():
        return rows
    for line in label_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            rows.append([float(p) for p in parts[:5]])
        except ValueError:
            continue
    return rows


def find_image(label_path: Path, images_dir: Path) -> Path | None:
    for ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
        p = images_dir / f"{label_path.stem}{ext}"
        if p.exists():
            return p
    return None


def collect_samples(dataset_root: Path, class_map: dict[int, int]) -> list[Sample]:
    samples: list[Sample] = []
    split_dirs = ["train", "valid", "test", "val"]

    for split in split_dirs:
        split_path = dataset_root / split
        labels_dir = split_path / "labels"
        images_dir = split_path / "images"
        if not labels_dir.exists() or not images_dir.exists():
            continue

        for label_file in labels_dir.glob("*.txt"):
            labels = parse_label_file(label_file)
            if not labels:
                continue

            image_path = find_image(label_file, images_dir)
            if image_path is None:
                continue

            mapped_ids: list[int] = []
            mapped_labels: list[list[float]] = []
            for row in labels:
                original_class = int(row[0])
                if original_class not in class_map:
                    continue
                mapped = class_map[original_class]
                mapped_ids.append(mapped)
                mapped_labels.append([float(mapped), row[1], row[2], row[3], row[4]])

            if not mapped_labels:
                continue

            counts = np.bincount(np.array(mapped_ids, dtype=np.int32), minlength=5)
            primary = int(np.argmax(counts))
            samples.append(
                Sample(
                    image_path=image_path,
                    label_path=label_file,
                    labels=mapped_labels,
                    mapped_primary=primary,
                )
            )
    return samples


def maybe_augment(
    image: np.ndarray,
    labels: list[list[float]],
    rng: random.Random,
) -> tuple[np.ndarray, list[list[float]]]:
    """Apply lightweight augmentations and update YOLO labels for flips."""
    out = image.copy()
    out_labels = [row.copy() for row in labels]

    # Horizontal flip
    if rng.random() < 0.5:
        out = cv2.flip(out, 1)
        for row in out_labels:
            row[1] = 1.0 - row[1]

    # Vertical flip
    if rng.random() < 0.2:
        out = cv2.flip(out, 0)
        for row in out_labels:
            row[2] = 1.0 - row[2]

    # Brightness/contrast
    if rng.random() < 0.8:
        alpha = rng.uniform(0.85, 1.20)
        beta = rng.uniform(-18, 18)
        out = cv2.convertScaleAbs(out, alpha=alpha, beta=beta)

    # Slight HSV jitter
    if rng.random() < 0.6:
        hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.int16)
        hsv[:, :, 0] = (hsv[:, :, 0] + rng.randint(-8, 8)) % 180
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] + rng.randint(-20, 20), 0, 255)
        hsv[:, :, 2] = np.clip(hsv[:, :, 2] + rng.randint(-20, 20), 0, 255)
        out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # Mild blur
    if rng.random() < 0.25:
        out = cv2.GaussianBlur(out, (3, 3), 0)

    # Tiny noise
    if rng.random() < 0.2:
        noise = np.random.normal(0, 5, out.shape).astype(np.int16)
        out = np.clip(out.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    return out, out_labels


def write_yolo_label(path: Path, labels: list[list[float]]) -> None:
    lines = []
    for cls_id, x, y, w, h in labels:
        lines.append(f"{int(cls_id)} {x:.6f} {y:.6f} {w:.6f} {h:.6f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_dirs(root: Path) -> None:
    for split in ("train", "valid", "test"):
        (root / split / "images").mkdir(parents=True, exist_ok=True)
        (root / split / "labels").mkdir(parents=True, exist_ok=True)


def split_for_index(i: int, target: int) -> str:
    train_n = int(target * 0.8)
    valid_n = int(target * 0.1)
    if i < train_n:
        return "train"
    if i < train_n + valid_n:
        return "valid"
    return "test"


def generate_balanced_dataset(
    samples: list[Sample],
    output_root: Path,
    target_per_class: int,
    seed: int,
) -> dict[int, int]:
    rng = random.Random(seed)

    pools: dict[int, list[Sample]] = {i: [] for i in range(5)}
    for s in samples:
        pools[s.mapped_primary].append(s)

    for class_id in range(5):
        if not pools[class_id]:
            raise RuntimeError(f"No source samples found for class {class_id}")

    if output_root.exists():
        shutil.rmtree(output_root)
    ensure_dirs(output_root)

    final_count: dict[int, int] = {i: 0 for i in range(5)}

    for class_id in range(5):
        src_pool = pools[class_id]
        rng.shuffle(src_pool)

        for i in range(target_per_class):
            split = split_for_index(i, target_per_class)
            out_img = output_root / split / "images" / f"c{class_id}_{i:04d}.jpg"
            out_lbl = output_root / split / "labels" / f"c{class_id}_{i:04d}.txt"

            source = src_pool[i % len(src_pool)]
            image = cv2.imread(str(source.image_path))
            if image is None:
                continue

            labels = [row.copy() for row in source.labels]
            for row in labels:
                row[0] = float(int(row[0]))

            if i >= len(src_pool):
                image, labels = maybe_augment(image, labels, rng)

            ok = cv2.imwrite(str(out_img), image)
            if not ok:
                continue
            write_yolo_label(out_lbl, labels)
            final_count[class_id] += 1

    yaml_text = {
        "train": str((output_root / "train" / "images").resolve()),
        "val": str((output_root / "valid" / "images").resolve()),
        "test": str((output_root / "test" / "images").resolve()),
        "nc": 5,
        "names": TARGET_CLASS_NAMES,
    }
    with (output_root / "data.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(yaml_text, f, sort_keys=False, allow_unicode=False)

    return final_count


def count_images_per_class(output_root: Path) -> dict[int, int]:
    counts = {i: 0 for i in range(5)}
    for split in ("train", "valid", "test"):
        labels_dir = output_root / split / "labels"
        for label_file in labels_dir.glob("*.txt"):
            rows = parse_label_file(label_file)
            if not rows:
                continue
            primary = int(rows[0][0])
            if primary in counts:
                counts[primary] += 1
    return counts


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)

    dataset_root = Path(args.input)
    output_root = Path(args.output)

    config = load_data_yaml(dataset_root)
    original_names = config.get("names")
    if not isinstance(original_names, list):
        raise ValueError("Invalid names in dataset yaml")

    class_map = build_class_map(original_names)
    samples = collect_samples(dataset_root, class_map)
    if not samples:
        raise RuntimeError("No samples found in input dataset")

    print("Source samples found:", len(samples))
    counts = {i: 0 for i in range(5)}
    for s in samples:
        counts[s.mapped_primary] += 1
    for i, name in enumerate(TARGET_CLASS_NAMES):
        print(f"  {name}: {counts[i]}")

    final_count = generate_balanced_dataset(
        samples=samples,
        output_root=output_root,
        target_per_class=args.target_per_class,
        seed=args.seed,
    )

    verified = count_images_per_class(output_root)

    print("\nBalanced dataset created at:", output_root)
    print("Requested target per class:", args.target_per_class)
    print("Final counts (generated):")
    for i, name in enumerate(TARGET_CLASS_NAMES):
        print(f"  {name}: {final_count[i]}")
    print("Verification counts (labels scanned):")
    for i, name in enumerate(TARGET_CLASS_NAMES):
        print(f"  {name}: {verified[i]}")
    print("\nDone.")


if __name__ == "__main__":
    main()
