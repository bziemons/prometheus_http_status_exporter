import asyncio
import signal
import sys
import time
import traceback
from typing import List

import aiohttp
from prometheus_client import start_http_server, Summary, Counter

DELAY_BETWEEN_CHECKS = 15

REQUEST_SUMMARY = Summary(
    "http_status_request_seconds", "Times the http(s) request was made", ["domain"]
)
REQUEST_STATUS_COUNTER = Counter(
    "http_status_request_response", "Response codes from http(s) requests", ["domain", "code"]
)


def stop_loop_on_exc(fut: asyncio.Future):
    loop = asyncio.get_event_loop()
    if fut.exception() is not None:
        traceback.print_exception(
            type(fut.exception()),
            fut.exception(),
            fut.exception().__traceback__,
        )
        loop.stop()


async def perpetual_domain_request(session: aiohttp.ClientSession, domain: str):
    # trace_config = aiohttp.TraceConfig()
    # async with aiohttp.ClientSession(trace_configs=[trace_config]) as session:
    start_time = time.perf_counter()
    async with session.get(domain) as response:
        REQUEST_STATUS_COUNTER.labels(domain=domain, code=response.status).inc()
        await response.text()
        end_time = time.perf_counter()
    REQUEST_SUMMARY.labels(domain=domain).observe(end_time - start_time)

    loop = asyncio.get_event_loop()
    await asyncio.sleep(DELAY_BETWEEN_CHECKS)
    task = loop.create_task(perpetual_domain_request(session, domain))
    task.add_done_callback(stop_loop_on_exc)


async def async_main(domain_list: List[str]):
    loop = asyncio.get_event_loop()
    session = aiohttp.ClientSession()
    for domain in domain_list:
        task = loop.create_task(
            perpetual_domain_request(session, domain),
            name=f"perpetual_domain_request for {domain}",
        )
        task.add_done_callback(stop_loop_on_exc)
        await asyncio.sleep(DELAY_BETWEEN_CHECKS / len(domain_list))
    print("Started all perpetual domain requests", file=sys.stderr, flush=True)


def main():
    # Start up the server to expose the metrics.
    start_http_server(9002)

    domain_list: List[str] = []
    with open("domains.txt", "r") as fhandle:
        for line in fhandle.readlines():
            if line:
                domain_list.append(line.strip())

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGTERM, lambda: loop.stop())
    loop.add_signal_handler(signal.SIGINT, lambda: loop.stop())
    task = loop.create_task(async_main(domain_list))
    task.add_done_callback(stop_loop_on_exc)
    loop.run_forever()


if __name__ == "__main__":
    main()
