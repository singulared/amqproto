import asyncio
from asyncio.streams import _DEFAULT_LIMIT

from async_timeout import timeout

from amqproto import protocol
from amqproto.util import override_signature
from amqproto.channel import Channel as SansioChannel
from amqproto.connection import Connection as SansioConnection

__all__ = ['Connection', 'run']


# pylint: disable=arguments-differ
class Channel(SansioChannel):

    def __init__(self, *args, reader, writer, **kwargs):
        super().__init__(*args, **kwargs)
        self.reader = reader
        self.writer = writer
        # Used to synchronize AMQP methods with OK replies
        self._reply_queue = asyncio.Queue()
        # Used to synchronize basic_get call with the message delivery
        self._get_queue = asyncio.Queue()
        # Used to await the broker acknowledgments in publisher confirms mode
        self._ack_event = None

        self._consumed_messages = asyncio.Queue()
        self._returned_messages = asyncio.Queue()

    async def _receive_method(self, method):
        await self._reply_queue.put(method)

    async def handle_frame(self, frame):
        coroutine, message = super().handle_frame(frame)
        if coroutine is not None:
            await coroutine
        if message is not None:
            if isinstance(message.delivery_info, protocol.BasicGetOK):
                await self._get_queue.put(message)
            elif isinstance(message.delivery_info, protocol.BasicReturn):
                await self._returned_messages.put(message)
            elif isinstance(message.delivery_info, protocol.BasicDeliver):
                await self._consumed_messages.put(message)

    async def _flush_outbound(self, has_reply):
        if self.reader.at_eof():
            raise ConnectionAbortedError
        self.writer.write(self.data_to_send())
        await self.writer.drain()
        if has_reply:
            reply = await self._reply_queue.get()
            if isinstance(reply, protocol.AMQPError):
                raise reply
            return reply

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        if not self.closed:
            reply_code = 0
            reply_text = ''
            if isinstance(exc, protocol.AMQPError):
                reply_code = exc.reply_code
                reply_text = exc.reply_text
            await self.close(reply_code, reply_text)

    @override_signature(SansioChannel.open)
    async def open(self):
        has_reply = super().open()
        return await self._flush_outbound(has_reply)

    async def _receive_ChannelOpenOK(self, method):
        super()._receive_ChannelOpenOK(method)
        await self._reply_queue.put(method)

    @override_signature(SansioChannel.close)
    async def close(self, *args, **kwargs):
        if not self.closed:
            has_reply = super().close(*args, **kwargs)
            await self._flush_outbound(has_reply)

    async def _receive_ChannelCloseOK(self, method):
        super()._receive_ChannelCloseOK(method)
        await self._reply_queue.put(method)

    async def _send_ChannelCloseOK(self, exc):
        super()._send_ChannelCloseOK(exc)
        await self._reply_queue.put(exc)

    @override_signature(SansioChannel.flow)
    async def flow(self, *args, **kwargs):
        has_reply = super().flow(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.exchange_declare)
    async def exchange_declare(self, *args, **kwargs):
        has_reply = super().exchange_declare(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.exchange_delete)
    async def exchange_delete(self, *args, **kwargs):
        has_reply = super().exchange_delete(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.exchange_bind)
    async def exchange_bind(self, *args, **kwargs):
        has_reply = super().exchange_bind(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.exchange_unbind)
    async def exchange_unbind(self, *args, **kwargs):
        has_reply = super().exchange_unbind(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.queue_declare)
    async def queue_declare(self, *args, **kwargs):
        has_reply = super().queue_declare(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.queue_bind)
    async def queue_bind(self, *args, **kwargs):
        has_reply = super().queue_bind(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.queue_unbind)
    async def queue_unbind(self, *args, **kwargs):
        has_reply = super().queue_unbind(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.queue_purge)
    async def queue_purge(self, *args, **kwargs):
        has_reply = super().queue_purge(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.queue_delete)
    async def queue_delete(self, *args, **kwargs):
        has_reply = super().queue_delete(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.basic_qos)
    async def basic_qos(self, *args, **kwargs):
        has_reply = super().basic_qos(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.basic_consume)
    async def basic_consume(self, *args, **kwargs):
        has_reply = super().basic_consume(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    async def _receive_BasicConsumeOK(self, method):
        super()._receive_BasicConsumeOK(method)
        await self._reply_queue.put(method)

    @override_signature(SansioChannel.basic_cancel)
    async def basic_cancel(self, *args, **kwargs):
        has_reply = super().basic_cancel(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    async def _receive_BasicCancelOK(self, method):
        super()._receive_BasicCancelOK(method)
        await self._reply_queue.put(method)

    @override_signature(SansioChannel.basic_publish)
    async def basic_publish(self, *args, **kwargs):
        has_reply = super().basic_publish(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.basic_get)
    async def basic_get(self, *args, **kwargs):
        has_reply = super().basic_get(*args, **kwargs)
        await self._flush_outbound(has_reply)
        return await self._get_queue.get()

    async def _receive_BasicGetOK(self, method):
        super()._receive_BasicGetOK(method)
        await self._reply_queue.put(method)

    async def _receive_BasicGetEmpty(self, method):
        super()._receive_BasicGetEmpty(method)
        await self._reply_queue.put(method)
        await self._get_queue.put(None)

    @override_signature(SansioChannel.basic_ack)
    async def basic_ack(self, *args, **kwargs):
        has_reply = super().basic_ack(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    async def _receive_BasicAck(self, method):
        super()._receive_BasicAck(method)
        if not self._unconfirmed_set:
            self._ack_event.set()
            self._ack_event = asyncio.Event()

    @override_signature(SansioChannel.basic_reject)
    async def basic_reject(self, *args, **kwargs):
        has_reply = super().basic_reject(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.basic_recover_async)
    async def basic_recover_async(self, *args, **kwargs):
        has_reply = super().basic_recover_async(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.basic_recover)
    async def basic_recover(self, *args, **kwargs):
        has_reply = super().basic_recover(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.basic_nack)
    async def basic_nack(self, *args, **kwargs):
        has_reply = super().basic_nack(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.tx_select)
    async def tx_select(self, *args, **kwargs):
        has_reply = super().tx_select(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.tx_commit)
    async def tx_commit(self, *args, **kwargs):
        has_reply = super().tx_commit(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.tx_rollback)
    async def tx_rollback(self, *args, **kwargs):
        has_reply = super().tx_rollback(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    @override_signature(SansioChannel.confirm_select)
    async def confirm_select(self, *args, **kwargs):
        self._ack_event = asyncio.Event()
        has_reply = super().confirm_select(*args, **kwargs)
        return await self._flush_outbound(has_reply)

    async def consumed_messages(self):
        while True:
            message = await self._consumed_messages.get()
            yield message

    async def returned_messages(self):
        while True:
            message = await self._returned_messages.get()
            yield message

    async def wait_for_confirmations(self):
        await self._ack_event.wait()


class Connection(SansioConnection):

    def __init__(self, host='localhost', port=5672, *,
                 limit=_DEFAULT_LIMIT, ssl=None, family=0, proto=0,
                 flags=0, sock=None, local_addr=None, server_hostname=None,
                 connect_timeout=10, **kwargs):
        super().__init__(**kwargs)
        self._connect_timeout = connect_timeout
        self._connect_args = {
            'host': host,
            'port': port,
            'limit': limit,
            'ssl': ssl,
            'family': family,
            'proto': proto,
            'flags': flags,
            'sock': sock,
            'local_addr': local_addr,
            'server_hostname': server_hostname,
        }
        self.reader = self.writer = None
        # Used to synchronize AMQP methods with OK replies
        self._reply_queue = asyncio.Queue()

        # An infinite loop of read/write communication, set
        # by open method
        self._communicate_task = None

    def Channel(self, *args, **kwargs):
        return Channel(*args, reader=self.reader, writer=self.writer, **kwargs)

    async def _receive_method(self, method):
        await self._reply_queue.put(method)

    async def open(self):
        with timeout(self._connect_timeout):
            self.reader, self.writer = await asyncio.open_connection(
                **self._connect_args
            )
            self.initiate_connection()
            await self._flush_outbound()
            self._communicate_task = asyncio.ensure_future(self._communicate())
            await self._reply_queue.get()

    async def _receive_ConnectionOpenOK(self, method):
        super()._receive_ConnectionOpenOK(method)
        await self._reply_queue.put(method)

    async def _communicate(self):
        data = bytearray()
        while not self.closed:
            frame_max = self.properties['frame_max']
            chunk = await self.reader.read(10 * frame_max)
            if not chunk:
                break
            data += chunk
            for frame in self.receive_frames(data):
                handler = self.handle_frame
                if frame.channel_id != 0:
                    channel = self.get_channel(frame.channel_id)
                    handler = channel.handle_frame
                coroutine = handler(frame)
                if coroutine is not None:
                    await coroutine
                await self._flush_outbound()
                del data[:frame.size]

    async def __aenter__(self):
        await self.open()
        return self

    async def close(self, reply_code, reply_text, class_id=0, method_id=0):
        if not self.closed:
            super().close(reply_code, reply_text, class_id, method_id)
            await self._flush_outbound()
            if not self.reader.at_eof():
                await self._reply_queue.get()
        # self._communicate_task.cancel()
        await self._communicate_task
        self.writer.close()

    async def _receive_ConnectionCloseOK(self, method):
        super()._receive_ConnectionCloseOK(method)
        await self._reply_queue.put(method)

    async def __aexit__(self, exc_type, exc, traceback):
        if not self.closed:
            reply_code = 0
            reply_text = ''
            if isinstance(exc, protocol.AMQPError):
                reply_code = exc.reply_code
                reply_text = exc.reply_text
            await self.close(reply_code, reply_text)

    async def _flush_outbound(self):
        if self.reader.at_eof():
            raise ConnectionAbortedError
        self.writer.write(self.data_to_send())
        await self.writer.drain()


# Copy-pasted from https://github.com/python/asyncio/pull/465
def _cleanup(main_task, loop):
    pending = []
    if not main_task.done():
        pending.append(main_task)
    try:
        # `shutdown_asyncgens` was added in Python 3.6; not all
        # event loops might support it.
        shutdown_asyncgens = loop.shutdown_asyncgens
        pending.append(shutdown_asyncgens())
    except AttributeError:
        pass

    try:
        if pending:
            pending = asyncio.gather(*pending)
            loop.run_until_complete(pending)
        main_task.result()
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def run(main, *, debug=False):
    """Run a coroutine.

    This function runs the passed coroutine, taking care of
    managing the asyncio event loop and finalizing asynchronous
    generators.

    This function cannot be called when another asyncio event loop
    is running.

    If debug is True, the event loop will be run in debug mode.

    This function handles KeyboardInterrupt exception in a way that
    the passed coroutine gets cancelled and KeyboardInterrupt
    is ignored. Therefore, to clean up an asyncio.CancelledError
    exception should be caught within the passed coroutine.

    This function should be used as a main entry point for
    asyncio programs, and should not be used to call asynchronous
    APIs.

    Example:

        from amqproto.io.asyncio import run

        async def main():
            await asyncio.sleep(1)
            print('hello')

        run(main())
    """
    if asyncio._get_running_loop() is not None:
        raise RuntimeError(
            "run() cannot be called from a running event loop")
    if not asyncio.iscoroutine(main):
        raise ValueError("a coroutine was expected, got {!r}".format(main))

    loop = asyncio.new_event_loop()
    main_task = loop.create_task(main)
    try:
        asyncio.set_event_loop(loop)

        if debug:
            loop.set_debug(True)

        return loop.run_until_complete(main_task)
    except KeyboardInterrupt:
        main_task.cancel()
    finally:
        _cleanup(main_task, loop)
