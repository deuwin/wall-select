import fcntl


class FileLock:
    def __init__(self, file_object, shared=True, blocking=True):
        self._operation = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
        if not blocking:
            self._operation = self._operation | fcntl.LOCK_NB
        self._file_desc = file_object.fileno()
        self._locked = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, type, value, traceback):
        self.release()

    def acquire(self):
        fcntl.flock(self._file_desc, self._operation)
        self._locked = True

    def release(self):
        if self._locked:
            fcntl.flock(self._file_desc, fcntl.LOCK_UN)
            self._locked = False

    @property
    def locked(self):
        return self._locked
