"""CIF parsing and validation.

This module provides functionality for loading data from
Crystallographic Information Files (:term:`CIF`). There are two main
functions `load_cif`, for parsing a CIF and returning the data in JSON
format and `validate_cif`, for checking a CIF does not contain any
syntax errors, informing the user of the location and type of error if
one is found.

Functions
---------
load_cif:
    Extract :term:`data items` from :term:`CIF` file and return a
    dictionary of :term:`data blocks`.
validate_cif:
    Validate :term:`CIF` file, and return True if no syntax errors
    are found, else raise a :class:`CIFParseError`.

Exceptions
----------
CIFParseError:
    Exception for all parse errors due to incorrect :term:`CIF` syntax.

"""

import collections
import re
from typing import Optional, Match, Pattern
import warnings


__all__ = ["load_cif", "validate_cif", "CIFParseError"]


def load_cif(filepath: str):
    """Extract and return :term:`data items` from a :term:`CIF`.

    The input CIF is read and split by :term:`data block`. The
    :term:`data block header` and data items are extracted for each
    data block and returned in a dictionary. Each one is represented
    by a `key: value` pair where the key is the data block header and
    the value is dictionary of the corresponding data items.

    Within each **data block**:

        Each non-:term:`loop` data item is stored in a key: value pair
        where the key and value are the :term:`data name` and
        :term:`data value` respectively.

        Loop data is stored similarly with the data items stored in
        key: value pairs as above but where the value is now a list of
        one or more data values assigned to that data name in the loop.

    Parameters
    ----------
    filepath: str
        Filepath to the input :term:`CIF`.

    Returns
    -------
    dict[dict]
        A dictionary of the extracted data organised by :term:`data
        block`.

    Raises
    ------
    CIFParseError:
        If a syntax error is found in the input raw :term:`CIF` data.

    Examples
    --------
    >>> from diffraction import load_cif

    Loading data for a single data block CIF:

    >>> calcite_data = load_cif("calcite.cif")

    The top level is a list of data block headers, which in this
    case has only one element.

    >>> calcite_data.keys()
    dict_keys(['data_calcite'])

    Individual data items are stored by data name.

    >>> calcite_data['data_calcite']['chemical_name_mineral']
    'Calcite'
    >>> calcite_data['data_calcite']['cell_volume']
    '366.63'

    Data items declared in a loop are stored in lists.

    >>> calcite_data['data_calcite']['atom_type_symbol']
    ['Ca2+', 'C4+', 'O2-']
    >>> calcite_data['data_calcite']['atom_type_oxidation_number']
    ['2', '4', '-2']

    A CIF with multiple data blocks is handled identically, where each
    is stored as a dictionary referenced by the corresponding data
    block header.

    >>> cif_data = load_cif("calcite_with_impurities.cif")
    >>> cif_data.keys()
    dict_keys(['data_calcite', 'data_aragonite', 'data_vaterite'])
    """

    if not filepath.lower().endswith('.cif'):
        warnings.warn(("No .cif file extension detected. Assuming the filetype"
                       "is CIF and continuing."), UserWarning)
    p = CIFParser(filepath)
    p.parse()
    return dict((data_block.header, data_block.data_items)
                for data_block in p.data_blocks)


def validate_cif(filepath: str):
    """Validate :term:`CIF` syntax

    The CIF is scanned and checked for syntax errors. If one is found
    the error is reported explicitly, along with line number where it
    occurs. Returns ``True`` if no errors are found.


    Parameters
    ----------
    filepath: str
        Filepath to the input :term:`CIF`.

    Returns
    -------
    bool:
         Return ``True`` if file syntax is valid.

    Raises
    ------
    CIFParseError:
        If a syntax error is found in the input raw :term:`CIF` data.

    Notes
    -----
    Syntax errors supported are:
        * Empty file
        * Missing inline :term:`data name`
        * Missing inline :term:`data value`
        * Unmatched loop :term:`data names` and :term:`data values`
        * Unclosed semicolon :term:`semicolon text field`

    Examples
    --------
    >>> validate_cif("path/to/valid_cif_file.cif")
    True
    >>> validate_cif("path/to/invalid_cif_file.cif")
    CIFParseError: Missing inline data name on line 3: "some_lone_data_value"
    """

    if not filepath.lower().endswith('.cif'):
        warnings.warn(("No .cif file extension detected. Assuming the filetype"
                       "is CIF and continuing."), UserWarning)
    with open(filepath, "r") as cif_file:
        raw_data = cif_file.read()
    v = CIFValidator(raw_data)
    return v.validate()


# Regular expressions used for parsing.
COMMENT_OR_BLANK = re.compile("\w*#.*|\s+$|^$")
DATA_BLOCK_HEADER = re.compile("(?:^|\n)(data_\S*)\s*", re.IGNORECASE)
LOOP = re.compile("(?:^|\n)loop_\s*", re.IGNORECASE)
DATA_NAME = re.compile("\s*_(\S+)")
DATA_NAME_START_LINE = re.compile("(?:^|\n)\s*_(\S+)")
DATA_VALUE = re.compile("\s*(\'[^\']+\'|\"[^\"]+\"|[^\s_#][^\s\'\"]*)")

DATA_VALUE_QUOTES = re.compile("^[\"\']?(.*?)[\"\']?$", re.DOTALL)
TEXT_FIELD = re.compile("[^_][^;]+")
SEMICOLON_DATA_ITEM = re.compile(
    "(?:^|\n){0.pattern}\n;\n((?:.(?<!\n;))*)\n;".format(DATA_NAME), re.DOTALL)
INLINE_DATA_ITEM = re.compile(
    "(?:^|\n){0.pattern}[^\S\n]+{1.pattern}".format(DATA_NAME, DATA_VALUE))


def strip_quotes(data_value: str):
    """Strip the ending quotes from a :term:`data value`"""
    return DATA_VALUE_QUOTES.match(data_value).group(1)


class DataBlock:
    """Object for storing and extracting data for given
    :term:`data block`

    Parameters
    ----------
        header
            The :term:`data block header` of the data block
        raw_data
            The raw data from the :term:`data block` not including the
            :term:`data block header`, with the comments and blank
            lines stripped out.

    Attributes
    ----------
        header: str
            The :term:`data block header` of the data block
        raw_data: str
            The raw data from the :term:`data block` from which the
            :term:`data items` are extracted. Data items are stripped
            out after extraction.
        data_items: dict
            A dictionary in which the :term:`data items` are stored
            as :term:`data name`: :term:`data value` pairs.

    """
    def __init__(self, header: str, raw_data: str) -> None:
        self.header = header
        self.raw_data = raw_data
        self.data_items = {}

    def extract_data_items(self, data_item_pattern: Pattern) -> None:
        """Extract matching (non-:term:`loop`) :term:`data items`

        Data items matching input `pattern` are extracted from
        `raw_data` and saved in the `data_item` dictionary. The
        matching data items are then removed from the `raw_data`
        string.

        Parameters
        ----------
        data_item_pattern:
            The compiled regex pattern which matches the
            :term:`data items` to be extracted. `pattern` must capture
            the :term:`data name` and :term:`data value`.

        Notes
        -----
        Only used for inline and semicolon :term:`data items`. However,
        any valid `data_item_pattern` should work.
        """
        data_items = data_item_pattern.findall(self.raw_data)
        for data_name, data_value in data_items:
            self.data_items[data_name] = strip_quotes(data_value)
        self.raw_data = data_item_pattern.sub("", self.raw_data)

    def extract_loop_data_items(self) -> None:
        """Extract all :term:`loop` :term:`data items` from raw data.

        For each :term:`data name`, a list of the corresponding
        :term:`data values' declared in the loop is extracted. These
        are then added to the `data_item` dictionary i.e.

          .. code-block:: python

            {"data_name_A": ["data_value_A1", "data_value_A2", ...],
             "data_name_B": ["data_value_B1", "data_value_B2", ...]}

        """
        loops = LOOP.split(self.raw_data)[1:]
        for loop in loops:
            data_names = DATA_NAME_START_LINE.findall(loop)
            for data_name in data_names:
                self.data_items[data_name] = []
            data_value_lines = loop.split("\n")[len(data_names):]
            for line in data_value_lines:
                data_values = DATA_VALUE.findall(line)
                for data_name, data_value in zip(data_names, data_values):
                    self.data_items[data_name].append(strip_quotes(data_value))

    def __repr__(self) -> str:
        """Representation of DataBlock, abbreviating raw data"""
        if len(self.raw_data) > 18:
            raw_data = "{:.15s}...".format(self.raw_data)
        else:
            raw_data = self.raw_data
        return "DataBlock({!r}, {!r}, {!r})".format(
            self.header, raw_data, self.data_items)

    def __eq__(self, other: "DataBlock") -> bool:
        return (self.header == other.header and
                self.data_items == other.data_items)


class CIFParser:
    """Class interface for parsing :term:`CIF` and exporting data

    The CIF is parsed and :term:`data items` are extracted for each
    :term:`data block`. Data is stored in a list of :class:`DataBlock`
    objects.

    Before parsing the CIF is checked and :class:`CIFParseError` is
    raised if a syntax error is found.

    Parameters
    ----------
    filepath
        Filepath to the input CIF.

    Attributes
    ----------
    raw_data: str
        The raw data from the file of which the comments and blank
        lines are stripped out.
    data_blocks: list[DataBlock]
        A list of data blocks.

    Examples
    --------
    >>> p = CIFParser("path/to/cif.cif")
    >>> p.parse()

    """

    def __init__(self, filepath: str) -> None:
        with open(filepath, "r") as cif:
            self.raw_data = cif.read()
        validator = CIFValidator(self.raw_data)
        validator.validate()
        self.data_blocks = []

    def _strip_comments_and_blank_lines(self) -> None:
        """Remove all comments and blank lines raw file string."""
        lines = self.raw_data.split("\n")
        keep = [line for line in lines if not COMMENT_OR_BLANK.match(line)]
        self.raw_data = "\n".join(keep)

    def _extract_data_blocks(self) -> None:
        """Split raw file string into data blocks and save as a list
        of :class:`DataBlock` objects.
        """
        self.data_blocks = []
        data_blocks = DATA_BLOCK_HEADER.split(self.raw_data)[1:]
        headers, blocks = data_blocks[::2], data_blocks[1::2]
        for header, data in zip(headers, blocks):
            self.data_blocks.append(DataBlock(header, data))

    def parse(self) -> None:
        """Parse the :term:`CIF` by :term:`data block` and extract
        the :term:`data items`.

        File is split into data blocks, each one saved in a
        :class:`DataBlock` object. Then for each data block, extract
        the semicolon, inline and loop data items.

        Notes
        -----
        When a data item is extracted, the corresponding raw CIF data
        is removed from the ``DataBlock.raw_data`` attribute and the
        extraction methods use this fact. Therefore, the data items
        must be extracted in the above order.

        For example, the ``DataBlock.extract_loop_data_items`` method
        assumes that only :term:`loop` data remains in the raw data
        and hence this must be done last.
        """
        self._strip_comments_and_blank_lines()
        self._extract_data_blocks()
        for data_block in self.data_blocks:
            data_block.extract_data_items(SEMICOLON_DATA_ITEM)
            data_block.extract_data_items(INLINE_DATA_ITEM)
            data_block.extract_loop_data_items()


class CIFParseError(Exception):
    """Exception for all parse errors due to incorrect syntax."""


class CIFValidator:
    """Class interface for validating CIF syntax.

    The CIF is scanned and checked for syntax errors. If one is found
    the error is reported explicitly, along with line number where it
    occurs.

    Parameters
    ----------
        raw_data
            The raw CIF contents.

    Attributes
    ----------
    lines: generator
        ``generator`` consisting of lines of the input CIF.
    current_line: str
        The current line being validated.
    line_number: int
        The line number of the `current_line`.

    Notes
    -----
    Current syntax errors supported are:
        * Empty file
        * Missing inline :term:`data name`
        * Missing inline :term:`data value`
        * Unmatched loop :term:`data names` and :term:`data values`
        * Unclosed semicolon :term:`semicolon text field`

    """
    def __init__(self, raw_data: str) -> None:
        """Initialises the :class:`CIFValidator` instance.

        The raw data of the CIF is split by the newline character and
        stored in a generator. The :class:`CIFValidator` instance is
        initialised on the first line, warning the user a if the file
        is empty.
        """
        if not raw_data or raw_data.isspace():
            warnings.warn("File is empty.")
        self.lines = (line for line in raw_data.split("\n"))
        self.current_line = next(self.lines)
        self.line_number = 1

    def error(self,
              message: str = None,
              line_number: int = None,
              line: str = None) -> None:
        """Raise error message reporting the line number and line contents."""
        if line_number is None:
            line_number, line = self.line_number, self.current_line
        raise CIFParseError('{} on line {}: "{}"'.format(
            message, line_number, line))

    def validate(self) -> Optional[bool]:
        """Validate the :term:`CIF` line by line.

        Perform context sensitive, line by line, scan through the CIF
        checking the syntax is valid. Current contexts treated are top
        level, inside a :term:`loop` and inside a :term:`semicolon
        text field`.

        Returns
        -------
        bool
            Return ``True`` if file syntax is valid.

        Raises
        ------
        CIFParserError
            When a syntax error is found in the input raw CIF data.
        """
        try:
            while True:
                if self._is_valid_single_line():
                    self._next_line()
                elif LOOP.match(self.current_line):
                    self._validate_loop()
                elif DATA_VALUE.match(self.current_line.lstrip()):
                    self.error("Missing inline data name")
                elif DATA_NAME.match(self.current_line):
                    self._validate_lone_data_name()
        except StopIteration:
            return True

    def _next_line(self) -> None:
        """Load next line of file and increment the current line number."""
        self.current_line = next(self.lines)
        self.line_number += 1

    def _validate_loop(self) -> None:
        """Validate :term:`loop` syntax.

        Raise a :class:`CIFParseError` if, for any row in the loop,
        the number of :term:`data values` does not match the number of
        declared :term:`data names`.

        Raises
        ------
        CIFParserError
            If number of :term:`data values` does not match the number
            of declared :term:`data names`.
        """
        loop_data_names = self._get_loop_data_names()
        while True:
            if COMMENT_OR_BLANK.match(self.current_line):
                self._next_line()
            elif self._is_loop_data_values():
                data_values = DATA_VALUE.findall(self.current_line)
                if len(data_values) != len(loop_data_names):
                    self.error("Unmatched data values to data names in loop")
                self._next_line()
            else:
                break

    def _get_loop_data_names(self) -> None:
        """ Extract :term:`data names` from a :term:`loop`

        Collect and return a the list of data names declared at the
        beginning of a loop. The first line containing anything but a
        valid data name, comment or blank line will signify the end of
        the data names and is assumed to be the beginning of the loop
        :term:`data values`.

        Returns
        -------
        loop_data_names
            list of :term:`data names` in :term:`loop`.
        """
        loop_data_names = []
        self._next_line()
        while True:
            if COMMENT_OR_BLANK.match(self.current_line):
                self._next_line()
            elif DATA_NAME.match(self.current_line):
                loop_data_names.append(DATA_NAME.match(self.current_line))
                self._next_line()
            else:
                break
        return loop_data_names

    def _validate_lone_data_name(self) -> None:
        """Validate isolated :term:`data name`.

        An isolated :term:`data name` could indicate a missing an
        inline :term:`data value`, in which case raise a
        :class:`CIFParseError`. Otherwise it denotes the beginning of
        a :term:`semicolon data item`, in which case that validate
        that separately.

        Raises
        ------
        CIFParseError:
            If :term:`data name` is not matched with corresponding
            :term:`data value`.
        """
        err_line_number, err_line = self.line_number, self.current_line
        try:
            self._next_line()
        # check if final line of file
        except StopIteration:
            self.error("Invalid inline data value",
                       err_line_number, err_line)
        # check if part of semicolon data item
        if self.current_line.startswith(";"):
            self._validate_semicolon_data_item()
        else:
            self.error("Invalid inline data value",
                       err_line_number, err_line)

    def _validate_semicolon_data_item(self) -> None:
        """Validates :term:`semicolon data item`.

        Check for closing semicolon and raise a :class:`CIFParseError`
        if the :term:`semicolon text field` is left unclosed.

        Raises
        ------
        CIFParseError:
            If the :term:`semicolon text field` has no closing ``;``.
        """
        self._next_line()
        # two line queue must be kept as if no closing semicolon is found,
        # then error occurred on previous line.
        previous_lines = collections.deque(maxlen=2)
        while True:
            if (COMMENT_OR_BLANK.match(self.current_line) or
                    TEXT_FIELD.match(self.current_line)):
                previous_lines.append((self.line_number, self.current_line))
                try:
                    self._next_line()
                # check if final line of file
                except StopIteration:
                    self.error("Unclosed semicolon text field")
            else:
                break
        if not self.current_line.startswith(";"):
            self.error("Unclosed semicolon text field",
                       *previous_lines[1])
        self._next_line()

    def _is_valid_single_line(self) -> bool:
        """Check if valid single line (in top level context)

        Check the line is valid and necessitates no further validation
        of current or following lines. (Top level context meaning not
        inside a :term:`loop` or :term:`semicolon text field`.)
        """
        return (COMMENT_OR_BLANK.match(self.current_line) or
                INLINE_DATA_ITEM.match(self.current_line) or
                DATA_BLOCK_HEADER.match(self.current_line))

    def _is_loop_data_values(self) -> bool:
        """Check if valid :term:`data value` in a :term:`loop` context."""
        return (DATA_VALUE.match(self.current_line) and not
                LOOP.match(self.current_line) and not
                DATA_BLOCK_HEADER.match(self.current_line))
