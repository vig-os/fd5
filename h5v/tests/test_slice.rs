use hdf5_metno::{File, Hyperslab, Selection, SliceOrIndex};

#[test]
fn test_hyperslab_slice_4d_to_2d() {
    let f = match File::open("demo2.fd5.h5") {
        Ok(f) => f,
        Err(_) => {
            eprintln!("Skipping test: demo2.fd5.h5 not found");
            return;
        }
    };
    let ds = f.dataset("volume").expect("open dataset");
    assert_eq!(ds.shape(), vec![5, 64, 128, 128]);

    // h_dim=0, w_dim=1
    let slice = vec![
        SliceOrIndex::Unlimited { start: 0, step: 1, block: 1 },
        SliceOrIndex::Unlimited { start: 0, step: 1, block: 1 },
        SliceOrIndex::Index(0),
        SliceOrIndex::Index(0),
    ];
    let sel = Selection::Hyperslab(Hyperslab::from(slice));
    let data: ndarray::Array2<u8> = ds.read_slice(sel).expect("read slice h0,w1");
    assert_eq!(data.shape(), &[5, 64]);

    // h_dim=2, w_dim=3 (the sensible default for TZYX)
    let slice2 = vec![
        SliceOrIndex::Index(0),
        SliceOrIndex::Index(0),
        SliceOrIndex::Unlimited { start: 0, step: 1, block: 1 },
        SliceOrIndex::Unlimited { start: 0, step: 1, block: 1 },
    ];
    let sel2 = Selection::Hyperslab(Hyperslab::from(slice2));
    let data2: ndarray::Array2<u8> = ds.read_slice(sel2).expect("read slice h2,w3");
    assert_eq!(data2.shape(), &[128, 128]);
}
