use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
    thread,
};

use ndarray::ArrayD;

#[derive(Debug, Clone)]
pub struct DatasetStats {
    pub min: f64,
    pub max: f64,
    pub mean: f64,
    pub std_dev: f64,
    pub count: usize,
}

impl DatasetStats {
    pub fn from_f64_iter(iter: impl Iterator<Item = f64>) -> Option<Self> {
        let mut count = 0usize;
        let mut min = f64::INFINITY;
        let mut max = f64::NEG_INFINITY;
        let mut sum = 0.0f64;
        let mut sum_sq = 0.0f64;
        for v in iter {
            if v.is_nan() {
                continue;
            }
            count += 1;
            if v < min { min = v; }
            if v > max { max = v; }
            sum += v;
            sum_sq += v * v;
        }
        if count == 0 {
            return None;
        }
        let mean = sum / count as f64;
        let variance = (sum_sq / count as f64) - mean * mean;
        let std_dev = if variance > 0.0 { variance.sqrt() } else { 0.0 };
        Some(Self { min, max, mean, std_dev, count })
    }

    pub fn display_string(&self) -> String {
        format!(
            "min={:.4} max={:.4} mean={:.4} std={:.4} ({} values)",
            self.min, self.max, self.mean, self.std_dev, self.count,
        )
    }
}

pub enum CachedDataset {
    ImageU8(ArrayD<u8>),
    ImageU16(ArrayD<u16>),
    ChartF64(Vec<f64>),
}

pub struct PreloadCache {
    data: HashMap<String, CachedDataset>,
    stats: HashMap<String, DatasetStats>,
    total_bytes: usize,
    max_bytes: usize,
}

pub type SharedCache = Arc<Mutex<PreloadCache>>;

impl PreloadCache {
    pub fn new(max_bytes: usize) -> Self {
        Self {
            data: HashMap::new(),
            stats: HashMap::new(),
            total_bytes: 0,
            max_bytes,
        }
    }

    pub fn get(&self, key: &str) -> Option<&CachedDataset> {
        self.data.get(key)
    }

    pub fn get_stats(&self, key: &str) -> Option<&DatasetStats> {
        self.stats.get(key)
    }

    pub fn insert_stats(&mut self, key: String, stats: DatasetStats) {
        self.stats.insert(key, stats);
    }

    pub fn insert(&mut self, key: String, value: CachedDataset, size: usize) -> bool {
        if self.total_bytes + size > self.max_bytes {
            return false;
        }
        self.total_bytes += size;
        self.data.insert(key, value);
        true
    }

    pub fn remaining(&self) -> usize {
        self.max_bytes.saturating_sub(self.total_bytes)
    }
}

pub struct DatasetInfo {
    pub filename: String,
    pub full_path: String,
    pub total_bytes: usize,
    pub is_image: bool,
    pub is_chart_f64: bool,
    pub bit_depth_8: bool,
}

pub fn spawn_preload(cache: SharedCache, mut datasets: Vec<DatasetInfo>, max_dataset_mb: usize) {
    // Sort ascending by size so small datasets are ready first
    datasets.sort_by_key(|d| d.total_bytes);
    let max_single_bytes = max_dataset_mb * 1024 * 1024;

    thread::spawn(move || {
        // Group datasets by filename to minimize file open/close
        let mut by_file: HashMap<String, Vec<&DatasetInfo>> = HashMap::new();
        for ds in &datasets {
            by_file.entry(ds.filename.clone()).or_default().push(ds);
        }

        for (filename, file_datasets) in &by_file {
            let file = match hdf5_metno::File::open(filename) {
                Ok(f) => f,
                Err(_) => continue,
            };

            for info in file_datasets {
                if info.total_bytes > max_single_bytes {
                    continue;
                }

                // Check remaining budget
                {
                    let guard = match cache.lock() {
                        Ok(g) => g,
                        Err(_) => return,
                    };
                    if guard.remaining() < info.total_bytes {
                        continue;
                    }
                }

                let ds = match file.dataset(&info.full_path) {
                    Ok(ds) => ds,
                    Err(_) => continue,
                };

                if info.is_image {
                    let cached = if info.bit_depth_8 {
                        match ds.read_dyn::<u8>() {
                            Ok(arr) => Some(CachedDataset::ImageU8(arr)),
                            Err(_) => None,
                        }
                    } else {
                        match ds.read_dyn::<u16>() {
                            Ok(arr) => Some(CachedDataset::ImageU16(arr)),
                            Err(_) => None,
                        }
                    };
                    if let Some(ref data) = cached {
                        // Compute stats for image datasets
                        let stats = match data {
                            CachedDataset::ImageU8(arr) => {
                                DatasetStats::from_f64_iter(arr.iter().map(|&v| v as f64))
                            }
                            CachedDataset::ImageU16(arr) => {
                                DatasetStats::from_f64_iter(arr.iter().map(|&v| v as f64))
                            }
                            _ => None,
                        };
                        if let Ok(mut guard) = cache.lock() {
                            if let Some(stats) = stats {
                                guard.insert_stats(info.full_path.clone(), stats);
                            }
                        }
                    }
                    if let Some(data) = cached {
                        if let Ok(mut guard) = cache.lock() {
                            guard.insert(info.full_path.clone(), data, info.total_bytes);
                        }
                    }
                } else if info.is_chart_f64 {
                    if let Ok(arr) = ds.read_1d::<f64>() {
                        let vec = arr.to_vec();
                        // Compute stats for chart datasets
                        let stats = DatasetStats::from_f64_iter(vec.iter().copied());
                        if let Ok(mut guard) = cache.lock() {
                            if let Some(stats) = stats {
                                guard.insert_stats(info.full_path.clone(), stats);
                            }
                            guard.insert(
                                info.full_path.clone(),
                                CachedDataset::ChartF64(vec),
                                info.total_bytes,
                            );
                        }
                    }
                }
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stats_known_values() {
        let data = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let stats = DatasetStats::from_f64_iter(data.into_iter()).unwrap();
        assert_eq!(stats.count, 5);
        assert!((stats.min - 1.0).abs() < 1e-10);
        assert!((stats.max - 5.0).abs() < 1e-10);
        assert!((stats.mean - 3.0).abs() < 1e-10);
        // std of [1,2,3,4,5] = sqrt(2) ≈ 1.4142
        assert!((stats.std_dev - 2.0_f64.sqrt()).abs() < 1e-10);
    }

    #[test]
    fn stats_single_value() {
        let stats = DatasetStats::from_f64_iter(std::iter::once(42.0)).unwrap();
        assert_eq!(stats.count, 1);
        assert!((stats.min - 42.0).abs() < 1e-10);
        assert!((stats.max - 42.0).abs() < 1e-10);
        assert!((stats.mean - 42.0).abs() < 1e-10);
        assert!((stats.std_dev).abs() < 1e-10);
    }

    #[test]
    fn stats_with_nans() {
        let data = vec![1.0, f64::NAN, 3.0, f64::NAN, 5.0];
        let stats = DatasetStats::from_f64_iter(data.into_iter()).unwrap();
        assert_eq!(stats.count, 3);
        assert!((stats.min - 1.0).abs() < 1e-10);
        assert!((stats.max - 5.0).abs() < 1e-10);
        assert!((stats.mean - 3.0).abs() < 1e-10);
    }

    #[test]
    fn stats_empty_returns_none() {
        let stats = DatasetStats::from_f64_iter(std::iter::empty());
        assert!(stats.is_none());
    }

    #[test]
    fn stats_display_formatting() {
        let stats = DatasetStats {
            min: 0.0,
            max: 100.0,
            mean: 50.0,
            std_dev: 28.8675,
            count: 100,
        };
        let s = stats.display_string();
        assert!(s.contains("min="));
        assert!(s.contains("max="));
        assert!(s.contains("100 values"));
    }
}
