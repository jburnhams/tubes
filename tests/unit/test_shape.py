from tubes.shape import arr, first, obj, objs


def test_each_gives_the_shape_asked_for_or_an_empty_one():
    assert obj({"a": 1}) == {"a": 1}
    assert obj([1]) == {} and obj(None) == {} and obj("x") == {}
    assert arr([1, 2]) == [1, 2]
    assert arr({"a": 1}) == [] and arr(None) == []
    assert objs([{"a": 1}, 2, None, {"b": 2}]) == [{"a": 1}, {"b": 2}]
    assert objs({"a": 1}) == []
    assert first([{"a": 1}, {"b": 2}]) == {"a": 1}
    assert first([]) == {} and first(["x"]) == {} and first(None) == {}
