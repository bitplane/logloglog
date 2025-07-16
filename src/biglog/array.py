import mmap
import os
import struct


class Array:
    CHUNK_SIZE_BYTES = 4096

    _DTYPE_MAP = {
        "b": ("b", 1),  # signed char
        "B": ("B", 1),  # unsigned char
        "h": ("h", 2),  # short
        "H": ("H", 2),  # unsigned short
        "i": ("i", 4),  # int
        "I": ("I", 4),  # unsigned int
        # Dynamically determine size for 'l' and 'L'
        "l": ("l", struct.calcsize("l")),  # long
        "L": ("L", struct.calcsize("L")),  # unsigned long
        "q": ("q", 8),  # long long
        "Q": ("Q", 8),  # unsigned long long
        "f": ("f", 4),  # float
        "d": ("d", 8),  # double
    }

    def __init__(self, filename, dtype, mode="r+b", initial_elements=0):
        if dtype not in self._DTYPE_MAP:
            raise ValueError(f"Unsupported dtype: {dtype}. Supported types are: {list(self._DTYPE_MAP.keys())}")

        self._filename = filename
        self._dtype = dtype
        self._dtype_format, self._element_size = self._DTYPE_MAP[dtype]
        self._file = None
        self._mmap = None
        self._len = 0
        self._capacity = 0
        self._capacity_bytes = 0  # Initialize _capacity_bytes here

        print(f"[DBA_INIT] Initializing with dtype={dtype}, element_size={self._element_size}")

        try:
            if "w" in mode or not os.path.exists(filename):
                # Create or truncate file
                self._file = open(filename, "w+b")
                bytes_needed = initial_elements * self._element_size
                chunks_needed = (bytes_needed + self.CHUNK_SIZE_BYTES - 1) // self.CHUNK_SIZE_BYTES
                self._capacity_bytes = chunks_needed * self.CHUNK_SIZE_BYTES
                self._capacity = self._capacity_bytes // self._element_size
                self._file.truncate(self._capacity_bytes)
                self._len = 0
                print(
                    f"[DBA_INIT] New file. initial_elements={initial_elements}, capacity={self._capacity}, capacity_bytes={self._capacity_bytes}"
                )
            else:
                # Open existing file
                self._file = open(filename, mode)
                current_file_size = os.fstat(self._file.fileno()).st_size
                self._len = current_file_size // self._element_size  # Actual number of elements

                # Calculate capacity based on current file size, rounded up to nearest chunk
                chunks_needed = (current_file_size + self.CHUNK_SIZE_BYTES - 1) // self.CHUNK_SIZE_BYTES
                self._capacity_bytes = chunks_needed * self.CHUNK_SIZE_BYTES
                self._capacity = self._capacity_bytes // self._element_size

                # If the file size is not already a multiple of the chunk size, truncate it to align.
                # This ensures consistency for mmap and future appends.
                if current_file_size < self._capacity_bytes:
                    self._file.truncate(self._capacity_bytes)
                print(
                    f"[DBA_INIT] Existing file. len={self._len}, capacity={self._capacity}, capacity_bytes={self._capacity_bytes}"
                )

            # Only mmap if the file has a non-zero size
            if self._capacity_bytes > 0 or (self._file and os.fstat(self._file.fileno()).st_size > 0):
                self._mmap = mmap.mmap(self._file.fileno(), 0)
                print(f"[DBA_INIT] mmap created with size {self._mmap.size()}")

        except Exception as e:
            if self._mmap:
                self._mmap.close()
            if self._file:
                self._file.close()
            raise RuntimeError(f"Failed to initialize Array: {e}")

    def __len__(self):
        return self._len

    def __getitem__(self, index):
        if not isinstance(index, int):
            raise TypeError("Index must be an integer")
        if not (0 <= index < self._len):
            raise IndexError("Index out of bounds")
        if not self._mmap:
            raise RuntimeError("Array is not memory-mapped. This should not happen if len > 0.")

        offset = index * self._element_size
        data = self._mmap[offset : offset + self._element_size]
        return struct.unpack(self._dtype_format, data)[0]

    def __setitem__(self, index, value):
        if not isinstance(index, int):
            raise TypeError("Index must be an integer")
        if not (0 <= index < self._len):
            raise IndexError("Index out of bounds")
        if not self._mmap:
            raise RuntimeError("Array is not memory-mapped. This should not happen if len > 0.")

        offset = index * self._element_size
        try:
            packed_value = struct.pack(self._dtype_format, value)
        except struct.error as e:
            raise TypeError(f"Value {value} cannot be packed as {self._dtype_format}: {e}")

        self._mmap[offset : offset + self._element_size] = packed_value

    def append(self, value):
        print(f"[DBA_APPEND] Appending value={value}, current_len={self._len}, current_capacity={self._capacity}")
        if self._len == self._capacity:
            # Need to resize
            if self._mmap:
                self._mmap.close()

            # Calculate how many elements fit into one CHUNK_SIZE_BYTES
            elements_in_chunk = self.CHUNK_SIZE_BYTES // self._element_size
            if elements_in_chunk == 0:  # Should not happen with current CHUNK_SIZE_BYTES and element_sizes
                elements_in_chunk = 1  # Fallback: add at least one element

            new_capacity = self._capacity + elements_in_chunk
            new_capacity_bytes = new_capacity * self._element_size

            print(
                f"[DBA_APPEND] Resizing: old_capacity={self._capacity}, new_capacity={new_capacity}, new_capacity_bytes={new_capacity_bytes}"
            )

            self._file.truncate(new_capacity_bytes)
            self._mmap = mmap.mmap(self._file.fileno(), 0)
            self._capacity = new_capacity
            self._capacity_bytes = new_capacity_bytes  # Update _capacity_bytes after resize
            print(f"[DBA_APPEND] Resized. New mmap size: {self._mmap.size()}")

        offset = self._len * self._element_size
        try:
            packed_value = struct.pack(self._dtype_format, value)
            print(f"[DBA_APPEND] Packed value size: {len(packed_value)}")
        except struct.error as e:
            raise TypeError(f"Value {value} cannot be packed as {self._dtype_format}: {e}")

        if not self._mmap:
            # This case should only happen if initial_elements was 0 and this is the very first append
            # Re-map the file now that it has a non-zero size
            self._mmap = mmap.mmap(self._file.fileno(), 0)
            print(f"[DBA_APPEND] First append, mmap created with size {self._mmap.size()}")

        self._mmap[offset : offset + self._element_size] = packed_value
        self._len += 1

    def flush(self):
        if self._mmap:
            self._mmap.flush()

    def close(self):
        if self._mmap:
            # Ensure all writes are on disk before truncating
            self._mmap.flush()
            self._mmap.close()
            self._mmap = None

        if self._file:
            # Only truncate if the file was opened in a writable mode
            # and if the current size is greater than the actual data length
            current_file_size = os.fstat(self._file.fileno()).st_size
            actual_data_bytes = self._len * self._element_size
            if current_file_size > actual_data_bytes:
                self._file.truncate(actual_data_bytes)
            self._file.close()
            self._file = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        # Fallback to close if not explicitly closed, but context manager is preferred
        # Check if _file is not None and not already closed
        if hasattr(self, "_file") and self._file and not self._file.closed:
            self.close()
