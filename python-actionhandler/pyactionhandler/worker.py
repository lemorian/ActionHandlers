import gevent
import greenlet
from greenlet import GreenletExit
import time
import logging

class Worker(object):
	def __init__(self, collection, node, response_queue, size=10, max_idle=300):
		self.logger = logging.getLogger('root')
		self.shutdown=False
		self.touch()
		self.node=node
		self.collection=collection
		self.task_queue=gevent.queue.JoinableQueue(maxsize=0)
		self.response_queue=response_queue
		self.greenlets=[gevent.spawn(self.handle_actions, max_idle) for count in range(size)]
		gevent.spawn(self.monitor)
		self.logger.info("New Worker for {node} created at {time}, can handle {size} tasks in parallel".format(
			node=self.node,time=time.strftime("%H:%M:%S", time.localtime()),size=size))

	def monitor(self):
		gevent.joinall(self.greenlets)
		self.logger.info("Worker for %s shutdown" % self.node)
		self.collection.remove_worker(self)

	def touch(self): self.mtime=time.time()

	def add_action(self, action):
		self.task_queue.put(action)
		self.logger.debug("[{anum}] Put Action on Worker queue for {node}".format(anum=action.num, node=self.node))

	def handle_actions(self, max_idle=300):
		def expired():
			return time.time() - self.mtime > max_idle
		def idle():
			return self.task_queue.unfinished_tasks == 0
		while not idle() or not expired() and not self.shutdown:
			try:
				with gevent.Timeout(0.1):
					action=self.task_queue.get()
			except gevent.Timeout:
				continue
			self.touch()
			try:
				with gevent.Timeout(action.timeout):
					self.logger.info("[{anum}] Executing {action}".format(
						anum=action.num, action=action))
					self.response_queue.put(action.__execute__())
			except gevent.Timeout:
				if callable(getattr(action, '__timeout__', None)):
					action.__timeout__(action.timeout)
				action.statusmsg = "[{anum}] Execution timed out after {to} seconds.".format(
					anum=action.num, to=action.timeout)
				action.success=False
				self.response_queue.put(action)
				self.logger.warning("[{anum}] Execution of {action} timed out after {to} seconds.".format(
					anum=action.num, action=action, to=action.timeout))
			finally:
				self.touch()
				self.task_queue.task_done()
				self.collection.task_queue.task_done()
				self.logger.debug("[{anum}] Removed Action from Worker queue for {node}".format(
					anum=action.num, node=self.node))
