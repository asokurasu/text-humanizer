import asyncio
import random
import uuid
from typing import List, Optional

import aiohttp
from fake_useragent import UserAgent
from tenacity import stop_after_attempt, retry, retry_if_not_exception_type, wait_random, retry_if_exception_type 

from data.config import MIN_PROXY_SCORE, CHECK_POINTS, STOP_ACCOUNTS_WHEN_SITE_IS_DOWN, NODE_TYPE

try:
    from data.config import SHOW_LOGS_RARELY
except ImportError:
    SHOW_LOGS_RARELY = ""

from .grass_sdk.extension import GrassWs
from .grass_sdk.website import GrassRest
from .utils import logger

from .utils.accounts_db import AccountsDB
from .utils.error_helper import raise_error, FailureCounter
from .utils.exception import WebsocketClosedException, LowProxyScoreException, ProxyScoreNotFoundException, \
    ProxyForbiddenException, ProxyError, WebsocketConnectionFailedError, FailureLimitReachedException, \
    NoProxiesException, ProxyBlockedException, SiteIsDownException, LoginException
from better_proxy import Proxy


class Grass(GrassWs, GrassRest, FailureCounter):
    # global_fail_counter = 0

    def __init__(self, _id: int, email: str, password: str, proxy: str = None, db: AccountsDB = None):
        self.proxy = Proxy.from_str(proxy).as_url if proxy else None
        super(GrassWs, self).__init__(email=email, password=password, user_agent=UserAgent().random, proxy=self.proxy)
        self.proxy_score: Optional[int] = None
        self.id: int = _id

        self.db: AccountsDB = db

        self.session: aiohttp.ClientSession = aiohttp.ClientSession(trust_env=True,
                                                                    connector=aiohttp.TCPConnector(ssl=False))

        self.proxies: List[str] = []
        self.is_extra_proxies_left: bool = True

        self.fail_count = 0
        self.limit = 7

    async def start(self):
        if self.db:
            self.proxies = await self.db.get_proxies_by_email(self.email)
        self.log_global_count(True)
        # logger.info(f"{self.id} | {self.email} | Starting...")
        while True:
            try:
                Grass.is_site_down()

                user_id = await self.enter_account()

                browser_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, self.proxy or ""))

                await self.run(browser_id, user_id)
            except LoginException as e:
                logger.warning(f"LoginException | {self.id} | {e}")
                return False
            except (ProxyBlockedException, ProxyForbiddenException) as e:
                # self.proxies.remove(self.proxy)
                msg = "Proxy forbidden"
            except ProxyError:
                msg = "Low proxy score"
            except WebsocketConnectionFailedError:
                msg = "Websocket connection failed"
                self.reach_fail_limit()
            except aiohttp.ClientError as e:
                msg = f"{str(e.args[0])[:30]}..." if "</html>" not in str(e) else "Html page response, 504"
            except FailureLimitReachedException as e:
                msg = "Failure limit reached"
                self.reach_fail_limit()
            except SiteIsDownException as e:
                msg = f"Site is down!"
                self.reach_fail_limit()
            else:
                msg = ""

            await self.failure_handler(
                is_raise=False,
            )

            await self.change_proxy()
            logger.info(f"{self.id} | Changed proxy to {self.proxy}. {msg}. Retrying...")

            await asyncio.sleep(random.uniform(20, 21))

    async def run(self, browser_id: str, user_id: str):
        while True:
            try:
                await self.connection_handler()

                await self.auth_to_extension(browser_id, user_id)

                if NODE_TYPE != "2x":
                    await self.handle_http_request_action()

                for i in range(10 ** 9):
                    if MIN_PROXY_SCORE and self.proxy_score is None:
                        if i < 3:
                            await self.handle_proxy_score(MIN_PROXY_SCORE, browser_id)
                        else:
                            raise ProxyScoreNotFoundException("Proxy score not found")

                    await self.send_ping()
                    await self.send_pong()

                    if SHOW_LOGS_RARELY:
                        if not (i % 10):
                            logger.info(f"{self.id} | Mined grass.")
                    else:
                        logger.info(f"{self.id} | Mined grass.")

                    if MIN_PROXY_SCORE and self.proxy_score is None:
                        await self.handle_proxy_score(MIN_PROXY_SCORE, browser_id)

                    if CHECK_POINTS and not (i % 100):
                        points = await self.get_points_handler()
                        await self.db.update_or_create_point_stat(self.id, self.email, points)
                        logger.info(f"{self.id} | Total points: {points}")
                    # if not (i % 1000):
                    #     total_points = await self.db.get_total_points()
                    #     logger.info(f"Total points in database: {total_points or 0}")
                    if i:
                        self.fail_reset()

                    await asyncio.sleep(random.randint(119, 120))
            except (WebsocketClosedException, ConnectionResetError, TypeError) as e:
                logger.info(f"{self.id} | {type(e).__name__}: {e}. Reconnecting...")
            # except ConnectionResetError as e:
            #     logger.info(f"{self.id} | Connection reset: {e}. Reconnecting...")
            # except TypeError as e:
            #     logger.info(f"{self.id} | Type error: {e}. Reconnecting...")
                # await self.delay_with_log(msg=f"{self.id} | Reconnecting with delay for some minutes...", sleep_time=60)
            # except Exception as e:
            #     logger.info(f"{self.id} | {traceback.format_exc()}")
            await self.failure_handler(limit=3)

            await asyncio.sleep(5, 10)

    async def claim_rewards(self):
        await self.enter_account()
        await self.claim_rewards_handler()

        logger.info(f"{self.id} | Claimed all rewards.")

    @retry(stop=stop_after_attempt(7),
           retry=(retry_if_exception_type(ConnectionError) | retry_if_not_exception_type(ProxyForbiddenException)),
           retry_error_callback=lambda retry_state:
           raise_error(WebsocketConnectionFailedError(f"{retry_state.outcome.exception()}")),
           wait=wait_random(7, 10),
           reraise=True)
    async def connection_handler(self):
        logger.info(f"{self.id} | Connecting...")
        await self.connect()
        logger.info(f"{self.id} | Connected")

    # @retry(stop=stop_after_attempt(3),
    #        retry=retry_if_not_exception_type(LowProxyScoreException),
    #        before_sleep=lambda retry_state, **kwargs: logger.info(f"{retry_state.outcome.exception()}"),
    #        wait=wait_random(1, 3))
    async def handle_proxy_score(self, min_score: int, browser_id: str):
        for _ in range(3):
            await asyncio.sleep(25, 30)
            if (proxy_score := await self.get_proxy_score_by_device_handler(browser_id)) is None:
                # logger.info(f"{self.id} | Proxy score not found for {self.proxy}. Guess Bad proxies! Continue...")
                # return None
                pass
            elif proxy_score >= min_score:
                self.proxy_score = proxy_score
                logger.success(f"{self.id} | Proxy score: {self.proxy_score}")
                return True
            else:
                raise LowProxyScoreException(f"{self.id} | Too low proxy score: {proxy_score} for {self.proxy}. Retrying...")

        logger.info(f"{self.id} | Proxy score not found for {self.proxy}. Waiting for score...")


    async def change_proxy(self):
        self.proxy = await self.get_new_proxy()

    async def get_new_proxy(self):
        while self.is_extra_proxies_left:
            if (proxy := await self.db.get_new_from_extra_proxies("ProxyList")) is not None:
                if proxy not in self.proxies:
                    if email := await self.db.proxies_exist(proxy):
                        if self.email == email:
                            self.proxies.insert(0, proxy)
                            break
                    else:
                        await self.db.add_account(self.email, proxy)
                        self.proxies.insert(0, proxy)
                        break
            else:
                self.is_extra_proxies_left = False

        return await self.next_proxy()

    async def next_proxy(self):
        if not self.proxies:
            await self.reset_with_delay(f"{self.id} | No proxies left. Use same proxy...", 30 * 60)
            return self.proxy
            # raise NoProxiesException(f"{self.id} | No proxies left. Exiting...")

        proxy = self.proxies.pop(0)
        self.proxies.append(proxy)

        return proxy

    @staticmethod
    def is_site_down():
        if STOP_ACCOUNTS_WHEN_SITE_IS_DOWN and Grass.is_global_error():
            logger.info(f"Site is down. Sleeping for non-working accounts...")
            raise SiteIsDownException()
