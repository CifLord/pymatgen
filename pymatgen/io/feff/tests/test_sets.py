from __future__ import annotations

import os
import shutil
import unittest

import numpy as np
import pytest

from pymatgen.core.structure import Molecule, Structure
from pymatgen.io.cif import CifParser
from pymatgen.io.feff.inputs import Atoms, Header, Potential, Tags
from pymatgen.io.feff.sets import FEFFDictSet, MPELNESSet, MPEXAFSSet, MPXANESSet
from pymatgen.util.testing import PymatgenTest


class FeffInputSetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header_string = """* This FEFF.inp file generated by pymatgen
TITLE comment: From cif file
TITLE Source:  CoO19128.cif
TITLE Structure Summary:  Co2 O2
TITLE Reduced formula:  CoO
TITLE space group: (P6_3mc), space number:  (186)
TITLE abc:  3.297078   3.297078   5.254213
TITLE angles: 90.000000  90.000000 120.000000
TITLE sites: 4
* 1 Co     0.333333     0.666667     0.503676
* 2 Co     0.666667     0.333333     0.003676
* 3 O     0.333333     0.666667     0.121324
* 4 O     0.666667     0.333333     0.621325"""
        cif_file = os.path.join(PymatgenTest.TEST_FILES_DIR, "CoO19128.cif")
        cls.structure = CifParser(cif_file).get_structures()[0]
        cls.absorbing_atom = "O"
        cls.mp_xanes = MPXANESSet(cls.absorbing_atom, cls.structure)

    def test_get_header(self):
        comment = "From cif file"
        header = str(self.mp_xanes.header(source="CoO19128.cif", comment=comment))
        print(header)

        ref = self.header_string.splitlines()
        last4 = [" ".join(line.split()[2:]) for line in ref[-4:]]
        for idx, line in enumerate(header.splitlines()):
            if idx < 9:
                assert line == ref[idx]
            else:
                s = " ".join(line.split()[2:])
                assert s in last4

    def test_getfefftags(self):
        tags = self.mp_xanes.tags.as_dict()
        assert tags["COREHOLE"] == "FSR", "Failed to generate PARAMETERS string"

    def test_get_feffPot(self):
        POT = str(self.mp_xanes.potential)
        d, dr = Potential.pot_dict_from_string(POT)
        assert d["Co"] == 1, "Wrong symbols read in for Potential"

    def test_get_feff_atoms(self):
        atoms = str(self.mp_xanes.atoms)
        assert atoms.splitlines()[3].split()[4] == self.absorbing_atom, "failed to create ATOMS string"

    def test_to_and_from_dict(self):
        f1_dict = self.mp_xanes.as_dict()
        f2 = MPXANESSet.from_dict(f1_dict)
        assert f1_dict == f2.as_dict()

    def test_user_tag_settings(self):
        tags_dict_ans = self.mp_xanes.tags.as_dict()
        tags_dict_ans["COREHOLE"] = "RPA"
        tags_dict_ans["EDGE"] = "L1"
        user_tag_settings = {"COREHOLE": "RPA", "EDGE": "L1"}
        mp_xanes_2 = MPXANESSet(self.absorbing_atom, self.structure, user_tag_settings=user_tag_settings)
        assert mp_xanes_2.tags.as_dict() == tags_dict_ans

    def test_eels_to_from_dict(self):
        elnes = MPELNESSet(
            self.absorbing_atom,
            self.structure,
            radius=5.0,
            beam_energy=100,
            beam_direction=[1, 0, 0],
            collection_angle=7,
            convergence_angle=6,
        )
        elnes_dict = elnes.as_dict()
        elnes_2 = MPELNESSet.from_dict(elnes_dict)
        assert elnes_dict == elnes_2.as_dict()

    def test_eels_tags_set(self):
        radius = 5.0
        user_eels_settings = {
            "ENERGY": "4 0.04 0.1",
            "BEAM_ENERGY": "200 1 0 1",
            "ANGLES": "2 3",
        }
        elnes = MPELNESSet(
            self.absorbing_atom,
            self.structure,
            radius=radius,
            user_eels_settings=user_eels_settings,
        )
        elnes_2 = MPELNESSet(
            self.absorbing_atom,
            self.structure,
            radius=radius,
            beam_energy=100,
            beam_direction=[1, 0, 0],
            collection_angle=7,
            convergence_angle=6,
        )
        assert elnes.tags["ELNES"]["ENERGY"] == user_eels_settings["ENERGY"]
        assert elnes.tags["ELNES"]["BEAM_ENERGY"] == user_eels_settings["BEAM_ENERGY"]
        assert elnes.tags["ELNES"]["ANGLES"] == user_eels_settings["ANGLES"]
        assert elnes_2.tags["ELNES"]["BEAM_ENERGY"] == [100, 0, 1, 1]
        assert elnes_2.tags["ELNES"]["BEAM_DIRECTION"] == [1, 0, 0]
        assert elnes_2.tags["ELNES"]["ANGLES"] == [7, 6]

    def test_charged_structure(self):
        # one Zn+2, 9 triflate, plus water
        # Molecule, net charge of -7
        xyz = os.path.join(PymatgenTest.TEST_FILES_DIR, "feff_radial_shell.xyz")
        m = Molecule.from_file(xyz)
        m.set_charge_and_spin(-7)
        # Zn should not appear in the pot_dict
        with pytest.warns(UserWarning, match="ION tags"):
            MPXANESSet("Zn", m)
        s = self.structure.copy()
        s.set_charge(1)
        with pytest.raises(ValueError, match="not supported"):
            MPXANESSet("Co", s)

    def test_reciprocal_tags_and_input(self):
        user_tag_settings = {"RECIPROCAL": "", "KMESH": "1000"}
        elnes = MPELNESSet(self.absorbing_atom, self.structure, user_tag_settings=user_tag_settings)
        assert "RECIPROCAL" in elnes.tags
        assert elnes.tags["TARGET"] == 3
        assert elnes.tags["KMESH"] == "1000"
        assert elnes.tags["CIF"] == "Co2O2.cif"
        assert elnes.tags["COREHOLE"] == "RPA"
        all_input = elnes.all_input()
        assert "ATOMS" not in all_input
        assert "POTENTIALS" not in all_input
        elnes.write_input()
        structure = Structure.from_file("Co2O2.cif")
        assert self.structure.matches(structure)
        os.remove("HEADER")
        os.remove("PARAMETERS")
        os.remove("feff.inp")
        os.remove("Co2O2.cif")

    def test_small_system_EXAFS(self):
        exafs_settings = MPEXAFSSet(self.absorbing_atom, self.structure)
        assert not exafs_settings.small_system
        assert "RECIPROCAL" not in exafs_settings.tags

        user_tag_settings = {"RECIPROCAL": ""}
        exafs_settings_2 = MPEXAFSSet(
            self.absorbing_atom,
            self.structure,
            nkpts=1000,
            user_tag_settings=user_tag_settings,
        )
        assert not exafs_settings_2.small_system
        assert "RECIPROCAL" not in exafs_settings_2.tags

    def test_number_of_kpoints(self):
        user_tag_settings = {"RECIPROCAL": ""}
        elnes = MPELNESSet(
            self.absorbing_atom,
            self.structure,
            nkpts=1000,
            user_tag_settings=user_tag_settings,
        )
        assert elnes.tags["KMESH"] == [12, 12, 7]

    def test_large_systems(self):
        struct = Structure.from_file(os.path.join(PymatgenTest.TEST_FILES_DIR, "La4Fe4O12.cif"))
        user_tag_settings = {"RECIPROCAL": "", "KMESH": "1000"}
        elnes = MPELNESSet("Fe", struct, user_tag_settings=user_tag_settings)
        assert "RECIPROCAL" not in elnes.tags
        assert "KMESH" not in elnes.tags
        assert "CIF" not in elnes.tags
        assert "TARGET" not in elnes.tags

    def test_postfeffset(self):
        self.mp_xanes.write_input(os.path.join(".", "xanes_3"))
        feff_dict_input = FEFFDictSet.from_directory(os.path.join(".", "xanes_3"))
        assert feff_dict_input.tags == Tags.from_file(os.path.join(".", "xanes_3/feff.inp"))
        assert str(feff_dict_input.header()) == str(Header.from_file(os.path.join(".", "xanes_3/HEADER")))
        feff_dict_input.write_input("xanes_3_regen")
        origin_tags = Tags.from_file(os.path.join(".", "xanes_3/PARAMETERS"))
        output_tags = Tags.from_file(os.path.join(".", "xanes_3_regen/PARAMETERS"))
        origin_mole = Atoms.cluster_from_file(os.path.join(".", "xanes_3/feff.inp"))
        output_mole = Atoms.cluster_from_file(os.path.join(".", "xanes_3_regen/feff.inp"))
        original_mole_dist = np.array(origin_mole.distance_matrix[0, :]).astype(np.float64)
        output_mole_dist = np.array(output_mole.distance_matrix[0, :]).astype(np.float64)
        original_mole_shell = [x.species_string for x in origin_mole]
        output_mole_shell = [x.species_string for x in output_mole]

        assert np.allclose(original_mole_dist, output_mole_dist)
        assert origin_tags == output_tags
        assert original_mole_shell == output_mole_shell

        shutil.rmtree(os.path.join(".", "xanes_3"))
        shutil.rmtree(os.path.join(".", "xanes_3_regen"))

        reci_mp_xanes = MPXANESSet(self.absorbing_atom, self.structure, user_tag_settings={"RECIPROCAL": ""})
        reci_mp_xanes.write_input("xanes_reci")
        feff_reci_input = FEFFDictSet.from_directory(os.path.join(".", "xanes_reci"))
        assert "RECIPROCAL" in feff_reci_input.tags

        feff_reci_input.write_input("Dup_reci")
        assert os.path.exists(os.path.join(".", "Dup_reci", "HEADER"))
        assert os.path.exists(os.path.join(".", "Dup_reci", "feff.inp"))
        assert os.path.exists(os.path.join(".", "Dup_reci", "PARAMETERS"))
        assert not os.path.exists(os.path.join(".", "Dup_reci", "ATOMS"))
        assert not os.path.exists(os.path.join(".", "Dup_reci", "POTENTIALS"))

        tags_original = Tags.from_file(os.path.join(".", "xanes_reci/feff.inp"))
        tags_output = Tags.from_file(os.path.join(".", "Dup_reci/feff.inp"))
        assert tags_original == tags_output

        stru_orig = Structure.from_file(os.path.join(".", "xanes_reci/Co2O2.cif"))
        stru_reci = Structure.from_file(os.path.join(".", "Dup_reci/Co2O2.cif"))
        assert stru_orig == stru_reci

        shutil.rmtree(os.path.join(".", "Dup_reci"))
        shutil.rmtree(os.path.join(".", "xanes_reci"))

    def test_post_distdiff(self):
        feff_dict_input = FEFFDictSet.from_directory(os.path.join(PymatgenTest.TEST_FILES_DIR, "feff_dist_test"))
        assert feff_dict_input.tags == Tags.from_file(
            os.path.join(PymatgenTest.TEST_FILES_DIR, "feff_dist_test/feff.inp")
        )
        assert str(feff_dict_input.header()) == str(
            Header.from_file(os.path.join(PymatgenTest.TEST_FILES_DIR, "feff_dist_test/HEADER"))
        )
        feff_dict_input.write_input("feff_dist_regen")
        origin_tags = Tags.from_file(os.path.join(PymatgenTest.TEST_FILES_DIR, "feff_dist_test/PARAMETERS"))
        output_tags = Tags.from_file(os.path.join(".", "feff_dist_regen/PARAMETERS"))
        origin_mole = Atoms.cluster_from_file(os.path.join(PymatgenTest.TEST_FILES_DIR, "feff_dist_test/feff.inp"))
        output_mole = Atoms.cluster_from_file(os.path.join(".", "feff_dist_regen/feff.inp"))
        original_mole_dist = np.array(origin_mole.distance_matrix[0, :]).astype(np.float64)
        output_mole_dist = np.array(output_mole.distance_matrix[0, :]).astype(np.float64)
        original_mole_shell = [x.species_string for x in origin_mole]
        output_mole_shell = [x.species_string for x in output_mole]

        assert np.allclose(original_mole_dist, output_mole_dist)
        assert origin_tags == output_tags
        assert original_mole_shell == output_mole_shell

        shutil.rmtree(os.path.join(".", "feff_dist_regen"))


if __name__ == "__main__":
    unittest.main()
