from src.translator import _split_into_batches


def test_split_small_list():
    segments = [{"id": i} for i in range(5)]
    batches = _split_into_batches(segments, batch_size=30)
    assert len(batches) == 1
    assert len(batches[0]) == 5


def test_split_exact_batch_size():
    segments = [{"id": i} for i in range(30)]
    batches = _split_into_batches(segments, batch_size=30)
    assert len(batches) == 1


def test_split_multiple_batches():
    segments = [{"id": i} for i in range(50)]
    batches = _split_into_batches(segments, batch_size=20)
    assert len(batches) == 3
    assert len(batches[0]) == 20
    assert len(batches[1]) == 20
    assert len(batches[2]) == 10


def test_split_empty_list():
    batches = _split_into_batches([], batch_size=20)
    assert len(batches) == 0
