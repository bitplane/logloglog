import pytest
import os
import tempfile
import struct

from biglog.array import Array


@pytest.fixture
def temp_filepath():
    fd, path = tempfile.mkstemp()
    os.close(fd)
    yield path
    os.remove(path)


@pytest.mark.parametrize(
    "dtype, initial_elements, expected_element_size",
    [
        ("b", 0, 1),
        ("i", 0, 4),
        ("d", 0, 8),
        ("i", 10, 4),
        ("f", 5, 4),
    ],
)
def test_init_new_file(temp_filepath, dtype, initial_elements, expected_element_size):
    array = Array(dtype, temp_filepath, "w+b", initial_elements)
    assert array._filename == temp_filepath
    assert array._dtype == dtype
    assert array._element_size == expected_element_size
    assert array._len == 0

    # Calculate expected capacity based on 4KB chunks
    bytes_needed = initial_elements * expected_element_size
    chunks_needed = (bytes_needed + Array.CHUNK_SIZE_BYTES - 1) // Array.CHUNK_SIZE_BYTES
    expected_capacity_bytes = chunks_needed * Array.CHUNK_SIZE_BYTES
    expected_capacity = expected_capacity_bytes // expected_element_size

    assert array._capacity == expected_capacity
    assert os.path.getsize(temp_filepath) == expected_capacity_bytes
    array.close()


def test_init_unsupported_dtype(temp_filepath):
    with pytest.raises(ValueError, match="Unsupported dtype"):
        Array("z", temp_filepath, "w+b")


def test_init_existing_file(temp_filepath):
    # Create a file with some data first
    with open(temp_filepath, "wb") as f:
        f.write(struct.pack("iii", 10, 20, 30))

    array = Array("i", temp_filepath, "r+b")
    assert array._len == 3
    # For existing files, capacity is aligned to the nearest 4KB chunk
    current_file_size = os.path.getsize(temp_filepath)
    expected_capacity = (
        (current_file_size + Array.CHUNK_SIZE_BYTES - 1)
        // Array.CHUNK_SIZE_BYTES
        * Array.CHUNK_SIZE_BYTES
        // array._element_size
    )
    assert array._capacity == expected_capacity
    assert array[0] == 10
    assert array[1] == 20
    assert array[2] == 30
    array.close()


def test_append_and_len(temp_filepath):
    array = Array("i", temp_filepath, "w+b")
    assert len(array) == 0

    array.append(1)
    assert len(array) == 1
    assert array[0] == 1

    array.append(2)
    assert len(array) == 2
    assert array[1] == 2
    array.close()


def test_append_triggers_resize(temp_filepath):
    # Use a small element size to easily trigger resize
    array = Array("B", temp_filepath, "w+b", 0)  # Changed to 'B'
    initial_capacity_bytes = array._capacity * array._element_size
    assert initial_capacity_bytes == 0  # Should start with 0 capacity if initial_elements is 0

    # Append enough elements to fill the first 4KB chunk
    elements_in_chunk = Array.CHUNK_SIZE_BYTES // array._element_size
    for i in range(elements_in_chunk):
        array.append(i % 256)  # Ensure value is within 'B' range
        assert len(array) == i + 1
        # Capacity should be elements_in_chunk until next append, or a multiple of elements_in_chunk
        assert array._capacity >= elements_in_chunk

    # Append one more to trigger resize
    array.append(elements_in_chunk % 256)  # Ensure value is within 'B' range
    assert len(array) == elements_in_chunk + 1
    assert array._capacity > elements_in_chunk  # Should have grown by another chunk
    array.close()


def test_append_type_error(temp_filepath):
    array = Array("i", temp_filepath, "w+b")
    with pytest.raises(TypeError, match="cannot be packed"):
        array.append("not an int")
    array.close()


def test_getitem_valid(temp_filepath):
    array = Array("i", temp_filepath, "w+b")
    array.append(100)
    array.append(200)
    assert array[0] == 100
    assert array[1] == 200
    array.close()


def test_getitem_out_of_bounds(temp_filepath):
    array = Array("i", temp_filepath, "w+b")
    array.append(10)
    with pytest.raises(IndexError, match="Index out of bounds"):
        _ = array[1]
    with pytest.raises(IndexError, match="Index out of bounds"):
        _ = array[-1]
    array.close()


def test_getitem_type_error(temp_filepath):
    array = Array("i", temp_filepath, "w+b")
    array.append(10)
    with pytest.raises(TypeError, match="Index must be an integer"):
        _ = array[0.5]
    array.close()


def test_setitem_valid(temp_filepath):
    array = Array("i", temp_filepath, "w+b")
    array.append(100)
    array.append(200)
    array[0] = 150
    assert array[0] == 150
    array[1] = 250
    assert array[1] == 250
    array.close()


def test_setitem_out_of_bounds(temp_filepath):
    array = Array("i", temp_filepath, "w+b")
    array.append(10)
    with pytest.raises(IndexError, match="Index out of bounds"):
        array[1] = 20
    with pytest.raises(IndexError, match="Index out of bounds"):
        array[-1] = 5
    array.close()


def test_setitem_type_error(temp_filepath):
    array = Array("i", temp_filepath, "w+b")
    array.append(10)
    with pytest.raises(TypeError, match="Index must be an integer"):
        array[0.5] = 20
    with pytest.raises(TypeError, match="cannot be packed"):
        array[0] = "not an int"
    array.close()


def test_flush(temp_filepath):
    array = Array("i", temp_filepath, "w+b")
    array.append(1)
    array.append(2)
    array.flush()
    array.close()  # Close the array to trigger truncation

    # Data should be on disk, and file size should be truncated
    array_reopen = Array("i", temp_filepath, "r+b")
    assert len(array_reopen) == 2
    assert array_reopen[0] == 1
    assert array_reopen[1] == 2
    array_reopen.close()


def test_close_truncates(temp_filepath):
    array = Array("i", temp_filepath, "w+b", 100)
    array.append(1)
    array.append(2)
    initial_file_size = os.path.getsize(temp_filepath)
    assert initial_file_size > (2 * array._element_size)  # Should be larger due to initial_elements
    array.close()
    # After close, file size should be exactly len * element_size
    assert os.path.getsize(temp_filepath) == (2 * array._element_size)


def test_close_multiple_times(temp_filepath):
    array = Array("i", temp_filepath, "w+b")
    array.append(1)
    array.close()
    array.close()  # Should not raise error


def test_context_manager(temp_filepath):
    with Array("i", temp_filepath, "w+b", 100) as array:
        array.append(10)
        array.append(20)

    # After exiting context, file should be closed and truncated
    assert os.path.exists(temp_filepath)
    assert os.path.getsize(temp_filepath) == (2 * struct.calcsize("i"))

    # Verify content by reopening
    array_reopen = Array("i", temp_filepath, "r+b")
    assert len(array_reopen) == 2
    assert array_reopen[0] == 10
    assert array_reopen[1] == 20
    array_reopen.close()


def test_persistence(temp_filepath):
    with Array("i", temp_filepath, "w+b") as array:
        for i in range(100):
            array.append(i)

    with Array("i", temp_filepath, "r+b") as array_reopen:
        assert len(array_reopen) == 100
        for i in range(100):
            assert array_reopen[i] == i


@pytest.mark.parametrize(
    "dtype, test_value",
    [
        ("b", 127),
        ("B", 255),
        ("h", 32767),
        ("H", 65535),
        ("i", 2147483647),
        ("I", 4294967295),
        ("l", 2147483647),
        ("L", 4294967295),
        ("q", 9223372036854775807),
        ("Q", 18446744073709551615),
        ("f", 3.14159),
        ("d", 2.718281828459045),
    ],
)
def test_different_dtypes(temp_filepath, dtype, test_value):
    array = Array(dtype, temp_filepath, "w+b")
    array.append(test_value)
    assert len(array) == 1
    assert array[0] == pytest.approx(test_value) if dtype in ["f", "d"] else test_value
    array.close()


def test_empty_array_access(temp_filepath):
    array = Array("i", temp_filepath, "w+b")
    assert len(array) == 0
    with pytest.raises(IndexError):
        _ = array[0]
    with pytest.raises(IndexError):
        array[0] = 1
    array.close()


def test_contains(temp_filepath):
    array = Array("i", temp_filepath, "w+b")
    array.append(10)
    array.append(20)
    array.append(30)
    assert 10 in array
    assert 20 in array
    assert 30 in array
    assert 40 not in array
    assert 5 not in array
    array.close()


def test_extend(temp_filepath):
    array = Array("i", temp_filepath, "w+b")
    array.extend([1, 2, 3])
    assert len(array) == 3
    assert array[0] == 1
    assert array[1] == 2
    assert array[2] == 3

    array.extend([4, 5])
    assert len(array) == 5
    assert array[3] == 4
    assert array[4] == 5
    array.close()


def test_iadd(temp_filepath):
    array = Array("i", temp_filepath, "w+b")
    array.append(1)
    array += [2, 3, 4]
    assert len(array) == 4
    assert array[0] == 1
    assert array[1] == 2
    assert array[2] == 3
    assert array[3] == 4
    array.close()


def test_imul(temp_filepath):
    array = Array("i", temp_filepath, "w+b")
    array.extend([1, 2])
    array *= 3
    assert len(array) == 6
    assert array[0] == 1
    assert array[1] == 2
    assert array[2] == 1
    assert array[3] == 2
    assert array[4] == 1
    assert array[5] == 2
    array.close()
