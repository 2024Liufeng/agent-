from skills.context_manager import get_similar_content_by_query
from skills.researcher import get_research_sources
from skills.writer import ReportGenerator
from tools.browser import BrowserManager
from tools.database import DatabaseManager


class DSResearcher:
    def __init__(
        self,
        query: str,
        thread_id: str,
        user_id: str,
    ):
        self.query = query
        self.thread_id = thread_id
        self.user_id = user_id
        self.visited_urls = set()
        self.research_sources = []
        self.context = []
        self.browser_manager = BrowserManager(self)
        self.database_manager = DatabaseManager(self)
        self.report_generator = ReportGenerator(self)

    async def conduct_research(self):
        # 浏览器工具运行时，BrowserManager 会直接保存抓取结果。
        await get_research_sources(
            self.query,
            thread_id=self.thread_id,
            user_id=self.user_id,
            researcher=self,
        )

        if not self.research_sources:
            return []

        self.context = get_similar_content_by_query(
            self.query,
            self.research_sources,
        )
        return self.context

    def write_report(self) -> str:
        report = self.report_generator.write_report()
        return report

    def generate_report_title(
        self,
        report: str,
    ) -> str:
        return self.report_generator.generate_title(
            report
        )
