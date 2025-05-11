from fastapi.testclient import TestClient
from main import app  # main.py から app をインポート

client = TestClient(app)


def test_read_root():
    """
    ルートエンドポイント ("/") のテスト。
    """
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == "Hello France"
    """
    ルートエンドポイント ("/") のテスト。
    """
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == "Hello Italy"


def test_read_item():
    """
    GET /items/{item_id} エンドポイントのテスト。
    """
    # クエリパラメータなしの場合
    response = client.get("/items/42")
    assert response.status_code == 200
    assert response.json() == {"item_id": 42, "q": None}

    # クエリパラメータありの場合
    response = client.get("/items/42?q=testquery")
    assert response.status_code == 200
    assert response.json() == {"item_id": 42, "q": "testquery"}


def test_read_item_not_found():
    """
    GET /items/{item_id} エンドポイントで、数値でないitem_idの場合のテスト。
    FastAPIが自動的に422 Unprocessable Entityを返すことを期待。
    """
    response = client.get("/items/foo")
    assert response.status_code == 422  # FastAPIによるバリデーションエラー


def test_update_item():
    """
    PUT /items/{item_id} エンドポイントのテスト。
    """
    item_data = {"name": "Test Item", "price": 9.99, "is_offer": True}
    response = client.put("/items/1", json=item_data)
    assert response.status_code == 200
    assert response.json() == {"item_name": "Test Item", "item_id": 1}


def test_update_item_invalid_payload():
    """
    PUT /items/{item_id} エンドポイントで、不正なペイロードの場合のテスト。
    """
    # price がない場合 (必須フィールド)
    item_data_missing_price = {"name": "Test Item No Price"}
    response = client.put("/items/2", json=item_data_missing_price)
    assert response.status_code == 422  # FastAPIによるバリデーションエラー

    # price の型が不正な場合
    item_data_invalid_price_type = {
        "name": "Test Item Invalid Price",
        "price": "not-a-float",
    }
    response = client.put("/items/3", json=item_data_invalid_price_type)
    assert response.status_code == 422  # FastAPIによるバリデーションエラー
