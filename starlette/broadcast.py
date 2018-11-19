import asyncio


class BroadcastMiddleware:
    def __init__(self, app, host='localhost', port=6379):
        self.app = app
        self.host = host
        self.port = port

    def __call__(self, scope):
        if scope['type'] == 'lifespan':
            return BroadcastLifespan(app, scope)
        return self.app(scope)


class BroadcastLifespan:
    def __init__(self, app, scope):
        self.inner = app(scope)
        self.send_buffer = asyncio.Queue()
        self.receive_buffer = asyncio.Queue()

    async def __call__(self, receive, send):
        inner_task = asyncio.create_task(
            self.inner(self.receive_buffer.get, self.send_buffer.put)
        )
        try:
            # Handle our own startup.
            message = await receive()
            assert message["type"] == "lifespan.startup"
            await self.startup()

            # Pass the message on to the next in the chain, and wait for the response.
            self.receive_buffer.put(message)
            message = await self.send_buffer.get()
            assert message["type"] == "lifespan.startup.complete"
            await send(message)

            # Handle our own shutdown.
            message = await receive()
            assert message["type"] == "lifespan.shutdown"
            await self.shutdown()

            # Pass the message on to the next in the chain, and wait for the response.
            self.receive_buffer.put(message)
            message = await self.send_buffer.get()
            assert message["type"] == "lifespan.shutdown.complete"
            await send(message)
        finally:
            await inner_task

    async def startup(self):
        print('startup')
        # self.pub = await asyncio_redis.Connection.create(self.host, self.port)
        # self.sub = await asyncio_redis.Connection.create(self.host, self.port)
        # self.sub = await sub.start_subscribe()
        # loop = asyncio.get_event_loop()
        # self.listener_task = loop.create_task(self.listen())

    async def shutdown(self):
        print('shutdown')
        # self.listener_task.cancel()

    # async def listen(self):
    #     while True:
    #         reply = await self.sub.next_published()
    #         print(reply)


# class RedisPubSubBackend:

#     async def subscribe(self, group_name):
#         pass
#
#     async def publish(self, group_name, message):
#         pass
#
#
# class BroadcastHandler:
#     def __init__(self, app, scope):
#         self.inner = app(scope)
#         self.receive = None
#         self.send = None
#         self.reciever_task = None
#         self.subscriber_task = None
#         self.subscriptions = set()
#         self.queue = asyncio.Queue()
#
#     async def __call__(self, receive, send):
#         self._receive = receive
#         self._send = send
#         try:
#             await self.inner(self.receive, self.send)
#         finally:
#             for group_name in self.subscriptions:
#                 await self.backend.unsubscribe(group_name, self.queue)
#
#     async def send(self, message):
#         if message['type'] == 'broadcast.subscribe':
#             group_name = message['group_name']
#             self.subscriptions.add(group_name, self.queue)
#             await self.backend.subscribe(group_name)
#         elif message['type'] == 'broadcast.message':
#             group_name = message['group_name']
#             message = message['message']
#             await self.backend.publish(group_name, message)
#
#     def receive(self):
#         if not self.subscriptions:
#             return await self._receive()
#
#         if self.reciever_task is None:
#             self.receiver_task = loop.create_task(self._receive())
#         if self.subscriber_task is None:
#             self.subscriber_task = loop.create_task(self.queue.get())
#
#         tasks = [self.receiver_task, self.subscriber_task]
#         done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
#         completed_task = done[0]
#         if completed_task is self.receiver_task:
#             self.receiver_task = None
#         else:
#             self.subscriber_task = None
#         return completed_task.result()
