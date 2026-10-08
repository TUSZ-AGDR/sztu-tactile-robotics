from pathlib import Path

import numpy as np
import pytest

from dexh13sim.taxel_template import TaxelTemplate


def test_load_template_converts_mm_to_m_and_normalizes_normals(tmp_path: Path):
    csv_path = tmp_path / "toy.csv"
    csv_path.write_text(
        "taxel_id,x_mm,y_mm,z_mm,nx,ny,nz\n"
        "0,1,2,3,0,0,2\n"
        "1,4,5,6,0,3,0\n",
        encoding="utf-8",
    )

    template = TaxelTemplate.load(csv_path, name="toy", expected_count=2)

    assert template.name == "toy"
    assert np.allclose(template.xyz_m, [[0.001, 0.002, 0.003], [0.004, 0.005, 0.006]])
    assert np.allclose(template.normals, [[0.0, 0.0, 1.0], [0.0, 1.0, 0.0]])


def test_load_template_rejects_non_contiguous_taxel_ids(tmp_path: Path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text(
        "taxel_id,x_mm,y_mm,z_mm,nx,ny,nz\n"
        "0,1,2,3,0,0,1\n"
        "2,4,5,6,0,0,1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="contiguous"):
        TaxelTemplate.load(csv_path, name="bad", expected_count=2)
