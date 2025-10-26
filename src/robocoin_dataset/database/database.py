import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


class RWLock:
    """读写锁：支持多个并发读，但写操作独占
    
    这比简单的互斥锁更高效，因为SQLite支持多个并发读操作。
    
    用法示例：
        lock = RWLock()
        
        # 读操作（可并发）
        with lock.read():
            # ... 读取数据 ...
        
        # 写操作（独占）
        with lock.write():
            # ... 修改数据 ...
    """
    def __init__(self):
        self._readers = 0  # 当前读锁持有者数量
        self._writers = 0  # 当前写锁持有者数量（0或1）
        self._read_ready = threading.Condition(threading.Lock())
        self._write_ready = threading.Condition(threading.Lock())
    
    def acquire_read(self):
        """获取读锁"""
        with self._read_ready:
            # 等待没有写锁
            while self._writers > 0:
                self._read_ready.wait()
            self._readers += 1
    
    def release_read(self):
        """释放读锁"""
        with self._read_ready:
            self._readers -= 1
            if self._readers == 0:
                # 通知等待的写锁
                with self._write_ready:
                    self._write_ready.notify()
    
    def acquire_write(self):
        """获取写锁（独占）"""
        with self._write_ready:
            # 等待没有读锁和写锁
            while self._readers > 0 or self._writers > 0:
                self._write_ready.wait()
            self._writers = 1
    
    def release_write(self):
        """释放写锁"""
        with self._write_ready:
            self._writers = 0
            # 通知所有等待的读锁和写锁
            with self._read_ready:
                self._read_ready.notify_all()
            self._write_ready.notify()
    
    @contextmanager
    def read(self):
        """读锁的上下文管理器"""
        self.acquire_read()
        try:
            yield
        finally:
            self.release_read()
    
    @contextmanager
    def write(self):
        """写锁的上下文管理器"""
        self.acquire_write()
        try:
            yield
        finally:
            self.release_write()


class DatasetDatabase:
    def __init__(self, db_file: Path) -> None:
        self.db_file = db_file.expanduser().absolute()
        self.engine = None
        self.session_local = None
        self._initialize()
        self._create_tables()
        # 🆕 使用读写锁替代简单互斥锁，支持并发读
        self._db_lock = RWLock()

    def _initialize(self) -> None:
        self.db_file = Path(self.db_file).expanduser().absolute()
        self.db_file.parent.mkdir(parents=True, exist_ok=True)

        database_url = f"sqlite:///{self.db_file}"
        self.engine = create_engine(database_url, connect_args={"check_same_thread": False})
        self.session_local = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_session(self) -> Generator[Session, None, None]:
        db = self.session_local()
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def with_session(self) -> Generator[Session, None, None]:
        """
        安全的上下文管理器，确保 session 正确关闭。
        推荐在同步代码中使用。
        
        🆕 使用写锁（独占），因为session可能包含写操作。
        如果只是纯读操作，可以考虑使用 with_read_session()（如果实现了的话）。
        """
        with self._db_lock.write():
            gen = self.get_session()
            session = next(gen)
            try:
                yield session
            except Exception:
                session.rollback()
                raise
            finally:
                gen.close()  # ✅ 触发 get_session 中的 finally

    def _create_tables(self) -> None:
        Base.metadata.create_all(bind=self.engine)
