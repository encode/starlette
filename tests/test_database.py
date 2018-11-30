import sqlalchemy
from starlette.applications import Starlette
from starlette.middleware.database import DatabaseMiddleware
from starlette.responses import JSONResponse
from starlette.testclient import TestClient
import os
import pytest

DATABASE_URL = os.environ['STARLETTE_TEST_DATABASE']

metadata = sqlalchemy.MetaData()

notes = sqlalchemy.Table('notes', metadata,
    sqlalchemy.Column('id', sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column('text', sqlalchemy.String),
    sqlalchemy.Column('completed', sqlalchemy.Boolean),
)

app = Starlette()
app.add_middleware(DatabaseMiddleware, database_url=DATABASE_URL)

@pytest.fixture(autouse=True, scope="module")
def create_test_database():
    engine = sqlalchemy.create_engine(DATABASE_URL)
    metadata.create_all(engine)
    yield
    engine.execute('DROP TABLE notes')


@app.route('/notes', methods=['GET'])
async def list_notes(request):
    query = sqlalchemy.select([notes])
    results = await request.db.fetch(query)
    content = [{'text': result['text'], 'completed': result['completed']} for result in results]
    return JSONResponse(content)


@app.route('/notes', methods=['POST'])
async def add_note(request):
    data = await request.json()
    query = notes.insert().values(text=data['text'], completed=data['completed'])
    await request.db.execute(query)
    return JSONResponse({'text': data['text'], 'completed': data['completed']})


def test_database():
    with TestClient(app) as client:
        response = client.post('/notes', json={'text': 'buy the milk', 'completed': True})
        assert response.status_code == 200
        response = client.post('/notes', json={'text': 'walk the dog', 'completed': False})
        assert response.status_code == 200
        response = client.get('/notes')
        assert response.status_code == 200
        assert response.json() == [
            {'text': 'buy the milk', 'completed': True},
            {'text': 'walk the dog', 'completed': False}
        ]
