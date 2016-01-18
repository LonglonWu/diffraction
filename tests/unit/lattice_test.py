from collections import OrderedDict

from numpy import array, array_equal, pi, sqrt
from numpy.testing import assert_almost_equal, assert_array_almost_equal
import pytest

from diffraction.cif.helpers import NUMERICAL_DATA_VALUE
from diffraction.lattice import DirectLattice, LATTICE_PARAMETER_KEYS

CALCITE_LATTICE = OrderedDict([("a", 4.99), ("b", 4.99), ("c", 17.002),
                               ("alpha", 90), ("beta", 90), ("gamma", 120)])
CALCITE_CIF = OrderedDict([("cell_length_a", "4.9900(2)"),
                           ("cell_length_b", "4.9900(2)"),
                           ("cell_length_c", "17.002(1)"),
                           ("cell_angle_alpha", "90."),
                           ("cell_angle_beta", "90."),
                           ("cell_angle_gamma", "90.")])

CALCITE_DIRECT_METRIC = array([[24.9001, -12.45005, 0],
                               [-12.45005, 24.9001, 0],
                               [0, 0, 289.068004]])


class TestCreatingDirectLatticeFromSequence:

    def test_error_if_lattice_parameter_missing_from_input_list(self):
        lattice_parameters = list(CALCITE_LATTICE.values())
        lattice_parameters_missing_one = lattice_parameters[:5]

        with pytest.raises(ValueError) as exception_info:
            l = DirectLattice(lattice_parameters_missing_one)
        assert str(exception_info.value) == "Missing lattice parameter from input"

    @pytest.mark.parametrize("invalid_value", ["abc", "123@%£", "1232.433.21"])
    def test_error_if_invalid_lattice_parameter_given(self, invalid_value):
        invalid_lattice_parameters = list(CALCITE_LATTICE.values())
        invalid_lattice_parameters[0] = invalid_value

        with pytest.raises(ValueError) as exception_info:
            l = DirectLattice(invalid_lattice_parameters)
        assert str(exception_info.value) == \
            "Invalid lattice parameter a: {}".format(invalid_value)

    def test_parameters_are_assigned_with_correct_type(self):
        lattice_parameters = CALCITE_LATTICE.values()
        l = DirectLattice(lattice_parameters)

        # test lattice parameters are assigned as floats
        for parameter, value in CALCITE_LATTICE.items():
            assert getattr(l, parameter) == value
            assert isinstance(getattr(l, parameter), float)

    def test_string_representation_of_crystal(self):
        lattice_parameters = CALCITE_LATTICE.values()
        l = DirectLattice(lattice_parameters)

        assert repr(l) == "DirectLattice({0})".format(
            [float(parameter) for parameter in lattice_parameters])
        assert str(l) == "DirectLattice({0})".format(
            [float(parameter) for parameter in lattice_parameters])


class TestCreatingDirectLatticeFromMapping:
    @pytest.mark.parametrize("missing_parameter", LATTICE_PARAMETER_KEYS)
    def test_error_if_parameter_missing_from_dict(self, missing_parameter):
        dict_with_missing_parameter = CALCITE_LATTICE.copy()
        del dict_with_missing_parameter[missing_parameter]

        with pytest.raises(ValueError) as exception_info:
            DirectLattice.from_dict(dict_with_missing_parameter)
        assert str(exception_info.value) == \
            "Parameter: '{}' missing from input dictionary".format(missing_parameter)

    def test_parameters_are_assigned_with_correct_type(self):
        c = DirectLattice.from_dict(CALCITE_LATTICE)

        for parameter in LATTICE_PARAMETER_KEYS:
            assert getattr(c, parameter) == CALCITE_LATTICE[parameter]
            assert isinstance(getattr(c, parameter), float)


class TestCreatingDirectLatticeFromCIF:
    @pytest.mark.parametrize("missing_data_name", CALCITE_CIF.keys())
    def test_error_if_parameter_is_missing_from_cif(self, missing_data_name, mocker):
        data_items_with_missing_item = CALCITE_CIF.copy()
        data_items_with_missing_item.pop(missing_data_name)
        mocker.patch("diffraction.lattice.load_data_block",
                     return_value=data_items_with_missing_item)

        with pytest.raises(ValueError) as exception_info:
            DirectLattice.from_cif("some/cif/file")
        assert str(exception_info.value) == \
            "Parameter: '{}' missing from input CIF".format(missing_data_name)

    def test_parameters_assigned_with_values_read_from_cif(self, mocker):
        load_data_block_mock = mocker.patch("diffraction.lattice.load_data_block",
                                            return_value="data_items")
        get_cif_data_mock = mocker.patch("diffraction.lattice.get_cif_data",
                                         return_value=CALCITE_LATTICE.values())

        l = DirectLattice.from_cif("some/single/data/block/cif")

        load_data_block_mock.assert_called_with("some/single/data/block/cif", None)
        get_cif_data_mock.assert_called_with("data_items", *CALCITE_CIF.keys())
        for data_name, (parameter, value) in zip(CALCITE_CIF.keys(), CALCITE_LATTICE.items()):
            assert getattr(l, parameter) == value


class TestAccessingComputedProperties:
    def test_can_get_lattice_parameters_as_a_list(self, mocker):
        mock = mocker.MagicMock(**CALCITE_LATTICE)
        mock.lattice_parameters = DirectLattice.lattice_parameters

        assert mock.lattice_parameters.fget(mock) == tuple(CALCITE_LATTICE.values())

    def test_lattice_parameters_updated_if_lattice_parameter_changed(self, mocker):
        mock = mocker.MagicMock(**CALCITE_LATTICE)
        mock.lattice_parameters = DirectLattice.lattice_parameters
        expected_lattice_parameters = (10,) + tuple(CALCITE_LATTICE.values())[1:]

        mock.a = 10
        assert mock.lattice_parameters.fget(mock) == expected_lattice_parameters

    def test_can_get_lattice_parameters_in_radians(self, mocker):
        mock = mocker.MagicMock(**CALCITE_LATTICE)
        mock.lattice_parameters_rad = DirectLattice.lattice_parameters_rad
        expected = tuple(CALCITE_LATTICE.values())[:3] + (pi / 2, pi / 2, 2 * pi / 3)

        assert mock.lattice_parameters_rad.fget(mock) == expected

    def test_direct_metric_is_calculated_correctly(self, mocker):
        lps_rad = tuple(CALCITE_LATTICE.values())[:3] + (pi / 2, pi / 2, 2 * pi / 3)
        mock = mocker.MagicMock(lattice_parameters_rad=lps_rad)
        mock.direct_metric = DirectLattice.direct_metric

        assert_array_almost_equal(mock.direct_metric.fget(mock), CALCITE_DIRECT_METRIC)

    def test_unit_cell_volume_is_calculated_correctly(self, mocker):
        mock = mocker.MagicMock(**CALCITE_LATTICE)
        mock.unit_cell_volume = DirectLattice.unit_cell_volume
        mock.direct_metric = CALCITE_DIRECT_METRIC
        a, c = CALCITE_LATTICE["a"], CALCITE_LATTICE["c"]
        expected = sqrt(3) / 2 * a * a * c

        assert_almost_equal(mock.unit_cell_volume.fget(mock), expected)
