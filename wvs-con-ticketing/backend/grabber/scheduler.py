"""任务调度器 — 管理抢票任务的定时执行"""

import logging
from datetime import datetime
from typing import Dict

logger = logging.getLogger("grabber.scheduler")


class TaskScheduler:
    """简单的任务调度管理"""

    def __init__(self, db_session_factory):
        self.db_factory = db_session_factory
        self._active_jobs: Dict[int, dict] = {}

    def schedule_order(self, order_id: int, target_time: datetime, config: dict):
        """调度一个抢票任务"""
        import threading

        delay = (target_time - datetime.now()).total_seconds()

        if delay < -60:
            logger.warning(f"Order#{order_id}: 开售时间已过 {abs(delay):.0f}s，放弃")
            return False

        job_info = {
            'order_id': order_id,
            'target_time': target_time,
            'config': config,
            'thread': None,
            'status': 'scheduled',
        }

        def run_grabber():
            try:
                job_info['status'] = 'running'
                logger.info(f"Order#{order_id}: 启动抢票引擎")

                from .engine import GrabberEngine
                db = self.db_factory()
                engine = GrabberEngine(order_id, config, db)
                result = engine.run(target_time)
                logger.info(f"Order#{order_id}: 结果 = {result['status']}")
                job_info['status'] = result['status']
            except Exception as e:
                logger.error(f"Order#{order_id}: 执行异常: {e}")
                job_info['status'] = 'error'
            finally:
                try:
                    db.close()
                except Exception:
                    pass

        if delay > 30:
            # 在开售前 10 秒启动引擎
            import time
            wait_time = max(0, delay - 10)

            def delayed_start():
                time.sleep(wait_time)
                run_grabber()

            t = threading.Thread(target=delayed_start, daemon=True)
        else:
            t = threading.Thread(target=run_grabber, daemon=True)

        t.start()
        job_info['thread'] = t
        self._active_jobs[order_id] = job_info
        logger.info(f"Order#{order_id}: 已调度，{delay:.0f}s 后执行")
        return True

    def get_job_status(self, order_id: int) -> dict:
        return self._active_jobs.get(order_id, {'status': 'not_found'})

    def cancel_order(self, order_id: int) -> bool:
        job = self._active_jobs.get(order_id)
        if job and job['status'] == 'scheduled':
            job['status'] = 'cancelled'
            return True
        return False

    @property
    def active_count(self):
        return sum(1 for j in self._active_jobs.values() if j['status'] in ('scheduled', 'running'))
