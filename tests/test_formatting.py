from core.formatting import format_number, format_station


def test_document_formatting():
    assert [format_number(v) for v in (0, 12.3, 99.945, None)] == [
        "0,00", "12,30", "99,95", "—",
    ]
    assert [format_station(v) for v in (0, 60, 200, 205.5, None)] == [
        "ПК 0+00,00", "ПК 0+60,00", "ПК 2+00,00", "ПК 2+05,50", "—",
    ]


def test_rounding_at_station_boundary():
    # Сначала округляем расстояние, затем разбиваем на пикет и остаток.
    assert format_station(199.995) == "ПК 2+00,00"
    assert format_station(199.994) == "ПК 1+99,99"
    assert format_number(-1.235) == "-1,24"
    assert format_number(-0.004) == "0,00"
