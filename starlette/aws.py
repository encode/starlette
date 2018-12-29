import asyncio
import base64
import urllib.parse

from starlette.types import Message
from starlette.applications import Starlette


class LambdaFunction(Starlette):

    def lambda_handler(self, event, context):
        connection_scope = {
            'type': 'http',
            'http_version': '1.1',
            'scheme': 'http',
            'method': event['httpMethod'],
            'root_path': '',
            'path': event['path'],
            'query_string': urllib.parse.urlencode(event['queryStringParameters']),
            'headers': event['headers'].items(),
            'x-aws-lambda': {
                'requestContext': event['requestContext'],
                'lambdaContext': context
            }
        }

        async def _receive() -> Message:
            body = event['body']
            if event['isBase64Encoded']:
                body = base64.standard_b64decode(body)
            return {
                'type': 'http.request',
                'body': body,
                'more_body': False
            }

        response = {}

        async def _send(message: Message) -> None:
            if message['type'] == 'http.response.start':
                response["statusCode"] = message['status']
                response["isBase64Encoded"] = False
                response["headers"] = {k.decode('utf-8'):v.decode('utf-8') for k, v in message['headers']}
            if message['type'] == 'http.response.body':
                response["body"] = message['body'].decode('utf-8')

        asgi = self(connection_scope)

        loop = asyncio.get_event_loop()
        task = loop.create_task(asgi(_receive, _send))
        loop.run_until_complete(task)

        return response