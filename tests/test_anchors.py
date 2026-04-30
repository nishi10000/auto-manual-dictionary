from auto_manual_dict.anchors import extract_anchors


def anchor_values(anchors, anchor_type):
    return {a.normalized_value for a in anchors if a.anchor_type == anchor_type}


def test_extracts_dtc_torque_voltage_part_number_and_deduplicates():
    text = "DTC P0A80 and P0A80. Tightening torque: 216 N·m. Voltage 12 V. Part No. 90915-YZZD1."
    anchors = extract_anchors(text)

    assert anchor_values(anchors, "dtc") == {"P0A80"}
    assert "216 Nm" in anchor_values(anchors, "torque")
    assert "12 V" in anchor_values(anchors, "voltage")
    assert "90915-YZZD1" in anchor_values(anchors, "part_number")


def test_extracts_image_name_anchor():
    anchors = extract_anchors("", images=["images/hub_nut.png", "../fig/engine_start.PNG"])
    assert anchor_values(anchors, "image_name") == {"hub_nut.png", "engine_start.png"}
