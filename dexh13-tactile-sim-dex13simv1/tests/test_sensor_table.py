from dexh13sim.sensor_table import SENSOR_TABLE, SENSOR_BY_ID, total_taxels


def test_sensor_table_matches_sdk_order_and_slices():
    assert len(SENSOR_TABLE) == 11
    assert total_taxels() == 1140

    expected = [
        (0, "sensor1", "index_proximal", "IP_M3025", 120, 0, 120),
        (1, "sensor2", "index_middle", "MP_M2324", 60, 120, 180),
        (2, "sensor3", "index_tip", "DP_M2826", 120, 180, 300),
        (3, "sensor4", "middle_proximal", "IP_M3025", 120, 300, 420),
        (4, "sensor5", "middle_middle", "MP_M2324", 60, 420, 480),
        (5, "sensor6", "middle_tip", "DP_M2826", 120, 480, 600),
        (6, "sensor7", "ring_proximal", "IP_M3025", 120, 600, 720),
        (7, "sensor8", "ring_middle", "MP_M2324", 60, 720, 780),
        (8, "sensor9", "ring_tip", "DP_M2826", 120, 780, 900),
        (9, "sensor10", "thumb_proximal", "IP_L5325", 120, 900, 1020),
        (10, "sensor11", "thumb_tip", "DP_L3530", 120, 1020, 1140),
    ]

    observed = [
        (
            item.sensor_id,
            item.sdk_name,
            item.name,
            item.template,
            item.count,
            item.start,
            item.end,
        )
        for item in SENSOR_TABLE
    ]
    assert observed == expected
    assert SENSOR_BY_ID[10].name == "thumb_tip"
