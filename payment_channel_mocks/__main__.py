import uvicorn

from payment_channel_mocks.app.core.config import MockSettings


def main() -> None:
    settings = MockSettings.from_env()
    uvicorn.run(
        "payment_channel_mocks.app.main:create_app",
        host=settings.host,
        port=settings.port,
        reload=False,
        factory=True,
    )


if __name__ == "__main__":
    main()

