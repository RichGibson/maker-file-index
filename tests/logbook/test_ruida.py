from maker_file_index.logbook.ruida import Setting, decode_settings, grid, swizzle, unswizzle


def n5(v):
    return [(v >> s) & 0x7F for s in (28, 21, 14, 7, 0)]


def p2(pct):
    r = round(pct * 0x3FFF / 100)
    return [(r >> 7) & 0x7F, r & 0x7F]


def scramble(cmds):
    return bytes(swizzle(b) for b in cmds)


def body(layer, speed_mm_s, lo, hi):
    return [0xCA, 0x02, layer, 0xC9, 0x02, *n5(int(speed_mm_s * 1000)),
            0xC6, 0x01, *p2(lo), 0xC6, 0x02, *p2(hi)]


def test_swizzle_roundtrip():
    assert all(unswizzle(swizzle(b)) == b for b in range(256))


def test_known_byte():
    assert unswizzle(0x82) == 0x88  # 0x82 starts many real stream lines


def test_body_settings():
    assert decode_settings(scramble(body(0, 14, 28, 28))) == [Setting(14.0, 28.0, 28.0)]


def test_header_only_layer_used_when_no_body():
    hdr = [0xC9, 0x04, 5, *n5(5000), 0xC6, 0x31, 5, *p2(10), 0xC6, 0x32, 5, *p2(10)]
    assert decode_settings(scramble(hdr)) == [Setting(5.0, 10.0, 10.0)]


def test_grid_detects_material_test():
    speeds = [5, 14, 23, 32, 41, 50]
    powers = [10, 28, 46, 64, 82, 100]
    s = [Setting(float(v), float(p), float(p)) for v in speeds for p in powers] + [Setting(60.0, 15.0, 25.0)]
    assert grid(s) == ([5.0, 14.0, 23.0, 32.0, 41.0, 50.0], [10.0, 28.0, 46.0, 64.0, 82.0, 100.0])


def test_grid_none_for_project_job():
    assert grid([Setting(12.0, 90.0, 90.0), Setting(50.0, 75.0, 75.0)]) is None


def test_garbage_does_not_raise():
    assert isinstance(decode_settings(bytes(range(256)) * 4), list)
