import pyarrow
import pytest

from kaxanuk.data_curator import DataColumn
from kaxanuk.data_curator.exceptions import DataColumnParameterError


class TestBooleanAnd:
    def test_one_column_disallowing_null_comparisons(self):
        column = DataColumn.load(
            [1, None, 0]
        )
        result = DataColumn.boolean_and(column)
        expected = DataColumn.load(
            [True, None, False]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )

    def test_one_column_allowing_null_comparisons(self):
        column = DataColumn.load(
            [1, None, 0]
        )
        result = DataColumn.boolean_and(
            column,
            allow_null_comparisons=True
        )
        expected = DataColumn.load(
            [True, None, False]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )

    def test_two_columns_disallowing_null_comparisons(self):
        column1 = DataColumn.load(
            [True,  False, True, False, None, False, None]
        )
        column2 = DataColumn.load(
            [False, False, True, True,  True, None,  None]
        )
        result = DataColumn.boolean_and(
            column1,
            column2
        )
        expected = DataColumn.load(
            [False, False, True, False,  None, None,  None]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )

    def test_two_columns_allowing_null_comparisons(self):
        column1 = DataColumn.load(
            [True,  False, True, False, None, False, None]
        )
        column2 = DataColumn.load(
            [False, False, True, True,  True, None,  None]
        )
        result = DataColumn.boolean_and(
            column1,
            column2,
            allow_null_comparisons=True
        )
        expected = DataColumn.load(
            [False, False, True, False, None, False,  None]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )

    def test_three_columns_disallowing_null_comparisons(self):
        column1 = DataColumn.load(
            [True,  False, True, False, None, False, None]
        )
        column2 = DataColumn.load(
            [False, False, True, True,  True, None,  None]
        )
        column3 = DataColumn.load(
            [True,  False,  True, False, None, False, None]
        )
        result = DataColumn.boolean_and(
            column1,
            column2,
            column3
        )
        expected = DataColumn.load(
            [False, False,  True, False, None, None,  None]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )

    def test_no_columns(self):
        with pytest.raises(DataColumnParameterError):
            DataColumn.boolean_and()

    def test_column_against_bool_disallowing_null_comparisons(self):
        column = DataColumn.load(
            [True,  False, None]
        )
        scalar = True
        result = DataColumn.boolean_and(
            column,
            scalar
        )
        expected = DataColumn.load(
            [True,  False,  None]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )

    def test_column_against_bool_allowing_null_comparisons(self):
        column = DataColumn.load(
            [True,  False, None]
        )
        scalar = True
        result = DataColumn.boolean_and(
            column,
            scalar,
            allow_null_comparisons=True
        )
        expected = DataColumn.load(
            [True,  False,  None]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )

    def test_column_against_scalar_disallowing_null_comparisons(self):
        column = DataColumn.load(
            [True,  False, None]
        )
        scalar = pyarrow.scalar(
            True,
            type=pyarrow.bool_()
        )
        result = DataColumn.boolean_and(
            column,
            scalar
        )
        expected = DataColumn.load(
            [True,  False, None]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )

    def test_column_against_scalar_allowing_null_comparisons(self):
        column = DataColumn.load(
            [True,  False, None]
        )
        scalar = pyarrow.scalar(
            True,
            type=pyarrow.bool_()
        )
        result = DataColumn.boolean_and(
            column,
            scalar,
            allow_null_comparisons=True
        )
        expected = DataColumn.load(
            [True,  False, None]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )


class TestBooleanOr:
    def test_one_column_disallowing_null_comparisons(self):
        column = DataColumn.load(
            [1, None, 0]
        )
        result = DataColumn.boolean_or(column)
        expected = DataColumn.load(
            [True, None, False]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )

    def test_one_column_allowing_null_comparisons(self):
        column = DataColumn.load(
            [1, None, 0]
        )
        result = DataColumn.boolean_or(
            column,
            allow_null_comparisons=True
        )
        expected = DataColumn.load(
            [True, None, False]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )

    def test_two_columns_disallowing_null_comparisons(self):
        column1 = DataColumn.load(
            [True,  False, True, False, None, False, None]
        )
        column2 = DataColumn.load(
            [False, False, True, True,  True, None,  None]
        )
        result = DataColumn.boolean_or(
            column1,
            column2
        )
        expected = DataColumn.load(
            [True,  False, True, True,  None, None,  None]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )

    def test_two_columns_allowing_null_comparisons(self):
        column1 = DataColumn.load(
            [True,  False, True, False, None, False, None]
        )
        column2 = DataColumn.load(
            [False, False, True, True,  True, None,  None]
        )
        result = DataColumn.boolean_or(
            column1,
            column2,
            allow_null_comparisons=True
        )
        expected = DataColumn.load(
            [True,  False, True, True,  True, None,  None]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )

    def test_three_columns_disallowing_null_comparisons(self):
        column1 = DataColumn.load(
            [True,  False, True, False, None, False, None]
        )
        column2 = DataColumn.load(
            [False, False, True, True,  True, None,  None]
        )
        column3 = DataColumn.load(
            [True,  False,  True, False, None, False, None]
        )
        result = DataColumn.boolean_or(
            column1,
            column2,
            column3
        )
        expected = DataColumn.load(
            [True,  False,  True, True,  None, None,  None]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )

    def test_no_columns(self):
        with pytest.raises(DataColumnParameterError):
            DataColumn.boolean_or()

    def test_column_against_bool_disallowing_null_comparisons(self):
        column = DataColumn.load(
            [True,  False, None]
        )
        scalar = True
        result = DataColumn.boolean_or(
            column,
            scalar
        )
        expected = DataColumn.load(
            [True,  True,  None]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )

    def test_column_against_bool_allowing_null_comparisons(self):
        column = DataColumn.load(
            [True,  False, None]
        )
        scalar = True
        result = DataColumn.boolean_or(
            column,
            scalar,
            allow_null_comparisons=True
        )
        expected = DataColumn.load(
            [True,  True,  True]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )

    def test_column_against_scalar_disallowing_null_comparisons(self):
        column = DataColumn.load(
            [True,  False, None]
        )
        scalar = pyarrow.scalar(
            True,
            type=pyarrow.bool_()
        )
        result = DataColumn.boolean_or(
            column,
            scalar
        )
        expected = DataColumn.load(
            [True,  True,  None]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )

    def test_column_against_scalar_allowing_null_comparisons(self):
        column = DataColumn.load(
            [True,  False, None]
        )
        scalar = pyarrow.scalar(
            True,
            type=pyarrow.bool_()
        )
        result = DataColumn.boolean_or(
            column,
            scalar,
            allow_null_comparisons=True
        )
        expected = DataColumn.load(
            [True,  True,  True]
        )

        assert DataColumn.fully_equal(
            result,
            expected,
            equal_nulls=True,
        )


class TestBool:
    def test_bool_of_equality_result_raises_type_error(self):
        col_a = DataColumn.load([1, 2, 3])
        col_b = DataColumn.load([9, 8, 7])

        with pytest.raises(TypeError):
            bool(col_a == col_b)

    def test_if_condition_on_equality_result_raises_type_error(self):
        # The exact user-facing trap: `if column_a == column_b:` must not silently take the
        # truthy branch. Without __bool__ this fell back to __len__ (truthy for any non-empty
        # pair), entering the branch even though no elements are equal.
        col_a = DataColumn.load([1, 2, 3])
        col_b = DataColumn.load([9, 8, 7])

        def _branch_on_columns():
            if col_a == col_b:
                return 'entered'
            return 'skipped'

        with pytest.raises(TypeError):
            _branch_on_columns()

    def test_bool_of_plain_column_raises_type_error(self):
        column = DataColumn.load([1, 2, 3])

        with pytest.raises(TypeError):
            bool(column)
