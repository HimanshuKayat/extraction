import asyncio

from tools.browser_tools import (
    browser_open,
    browser_inspect,
    browser_close,
)


async def main():

    print("OPENING...")
    print(
        await browser_open(
            "https://example.com/"
        )
    )

    print("INSPECTING...")
    print(
        await browser_inspect()
    )

    print("CLOSING...")
    print(
        await browser_close()
    )


asyncio.run(main())
