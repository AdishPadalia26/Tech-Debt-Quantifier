"""Repository Profiler - Analyzes repo for tech stack, team, and AI usage.

Provides complete repository profiling:
- detect_tech_stack: Identifies frameworks, libraries, databases
- profile_team: Analyzes team size, activity, bus factor
- get_stack_specific_rates: Searches for technology-specific rates
- calculate_multipliers: Derives repo-specific cost multipliers
- detect_ai_generated_code: Identifies suspected AI-generated files
"""

import ast
import logging
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pydriller import Repository

from core.cache_manager import get_cache
from constants import SKIP_DIRS
from intelligence.rate_agent import RateIntelligenceAgent

logger = logging.getLogger(__name__)

CATEGORIES = {
    "frameworks": [
        "django", "flask", "fastapi", "express", "nextjs", "react", "vue",
        "angular", "rails", "spring", "springboot", "laravel", "asp.net",
        "dotnet", "Phoenix", "Next.js", "Nuxt", "SvelteKit",
    ],
    "ai_ml": [
        "openai", "anthropic", "langchain", "langgraph", "transformers",
        "torch", "tensorflow", "sklearn", "xgboost", "llama", "sentence_transformers",
        "groq", "cohere", "mistral", "crewai", "autogen", "vllm", "huggingface",
        "gemini", "claude", "bedrock",
    ],
    "vector_dbs": [
        "pinecone", "weaviate", "chromadb", "qdrant", "faiss", "milvus",
    ],
    "databases": [
        "psycopg2", "pymongo", "redis", "elasticsearch", "cassandra",
        "sqlalchemy", "asyncpg", "motor", "snowflake", "databricks", "duckdb",
        "postgresql", "mysql", "mariadb", "mongodb", "sqlite3", "supabase",
    ],
    "cloud": [
        "boto3", "google-cloud", "azure", "pulumi", "aws", "gcp",
    ],
    "infra": [
        "kafka", "rabbitmq", "celery", "airflow", "kubernetes", "terraform",
        "prometheus", "grafana", "docker", "nomad",
    ],
    "testing": [
        "pytest", "jest", "mocha", "rspec", "junit", "hypothesis",
        "factory_boy", "playwright", "selenium", "cypress",
    ],
}

GENERIC_VAR_NAMES = {
    "data", "result", "response", "output", "temp", "x", "y", "res",
    "obj", "val", "item", "info", "dict", "list", "arr", "tmp",
}


class RepoProfiler:
    """Profiles repositories for tech stack, team, and AI usage."""

    def __init__(self) -> None:
        self._cache = get_cache()
        self._rate_agent = RateIntelligenceAgent()

    def detect_tech_stack(self, repo_path: str) -> dict[str, Any]:
        """Detect technology stack from dependency files.
        
        Args:
            repo_path: Path to repository
            
        Returns:
            Tech stack profile with all detected technologies
        """
        cache_key = self._cache.make_key("tech_stack", repo_path)
        
        if self._cache.is_fresh(cache_key, "repo_profile"):
            cached = self._cache.get(cache_key, "repo_profile")
            if cached and "tech_stack" in cached:
                return cached["tech_stack"]

        all_deps: dict[str, str] = {}
        detected: dict[str, list[str]] = {
            "frameworks": [], "ai_ml": [], "vector_dbs": [],
            "databases": [], "cloud": [], "infra": [], "testing": [],
        }

        dep_files = [
            "requirements.txt", "pyproject.toml", "Pipfile", "setup.py",
            "package.json", "yarn.lock", "go.mod", "Cargo.toml",
            "Dockerfile", "docker-compose.yml",
        ]

        for root, _, files in os.walk(repo_path):
            if any(skip in root for skip in SKIP_DIRS):
                continue

            for file in files:
                if file in dep_files or ".github/workflows" in root:
                    file_path = os.path.join(root, file)
                    deps = self._parse_dep_file(file_path, file)
                    all_deps.update(deps)

        all_deps_lower = {k.lower(): v for k, v in all_deps.items()}

        for category, keywords in CATEGORIES.items():
            for keyword in keywords:
                if keyword.lower() in all_deps_lower:
                    detected[category].append(keyword)

        ext_counts: Counter[str] = Counter()
        for root, _, files in os.walk(repo_path):
            if any(skip in root for skip in SKIP_DIRS):
                continue
            for file in files:
                if "." in file:
                    ext = file.rsplit(".", 1)[1].lower()
                    if ext not in {"txt", "md", "rst", "json", "yml", "yaml",
                                   "toml", "lock", "cfg", "ini", "pyc"}:
                        ext_counts[ext] += 1

        primary_lang = ext_counts.most_common(1)[0][0] if ext_counts else "py"

        has_tests = any(
            f in str(dep_files) for f in ["pytest", "jest", "rspec", "junit"]
        ) or any(
            os.path.exists(os.path.join(repo_path, d))
            for d in ["tests", "test", "__tests__", "spec"]
        )

        has_ci = os.path.exists(os.path.join(repo_path, ".github", "workflows"))
        has_docker = any(
            os.path.exists(os.path.join(repo_path, f))
            for f in ["Dockerfile", "docker-compose.yml"]
        )

        result = {
            "primary_language": primary_lang,
            "all_languages": dict(ext_counts.most_common(10)),
            "frameworks": list(set(detected["frameworks"])),
            "ai_ml_libraries": list(set(detected["ai_ml"])),
            "vector_dbs": list(set(detected["vector_dbs"])),
            "databases": list(set(detected["databases"])),
            "cloud": list(set(detected["cloud"])),
            "infra": list(set(detected["infra"])),
            "testing_frameworks": list(set(detected["testing"])),
            "has_tests": has_tests,
            "has_ci_cd": has_ci,
            "has_docker": has_docker,
            "dependency_count": len(all_deps),
            "uses_ai": len(detected["ai_ml"]) > 0,
            "all_dependencies": all_deps,
        }

        return result

    def _parse_dep_file(self, file_path: str, filename: str) -> dict[str, str]:
        """Parse dependency file to extract package versions."""
        deps = {}

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if filename == "requirements.txt":
                for line in content.split("\n"):
                    line = line.split("#")[0].strip()
                    if line and not line.startswith("-"):
                        parts = re.split(r"[=<>!~]", line)
                        if parts:
                            deps[parts[0].strip()] = parts[1].strip() if len(parts) > 1 else ""

            elif filename in ("package.json",):
                try:
                    import json
                    data = json.loads(content)
                    for dep_type in ["dependencies", "devDependencies"]:
                        if dep_type in data:
                            deps.update(data[dep_type])
                except Exception:
                    pass

            elif filename in ("pyproject.toml", "setup.py"):
                matches = re.findall(r'["\']?([a-zA-Z0-9_-]+)\s*[=<>]+', content)
                for match in matches:
                    deps[match] = ""

        except Exception as e:
            logger.debug(f"Error parsing {file_path}: {e}")

        return deps

    def profile_team(self, repo_path: str) -> dict[str, Any]:
        """Profile the development team using git history.
        
        Args:
            repo_path: Path to repository
            
        Returns:
            Team profile with size, activity, bus factor
        """
        cache_key = self._cache.make_key("team_profile", repo_path)

        if self._cache.is_fresh(cache_key, "repo_profile"):
            cached = self._cache.get(cache_key, "repo_profile")
            if cached and "team" in cached:
                return cached["team"]

        try:
            repo = Repository(repo_path, num_workers=1)
            commits = list(repo.traverse_commits())

            if not commits:
                return self._default_team_profile()

            author_commits: Counter[str] = Counter()
            all_authors = set()
            dates = []

            for commit in commits:
                author = commit.author.email
                author_commits[author] += 1
                all_authors.add(author)
                dates.append(commit.author_date)

            dates.sort()
            repo_age_days = (datetime.now() - dates[0]).days if dates else 0

            cutoff = datetime.now() - timedelta(days=90)
            active_authors = {
                a for c in commits
                if c.author_date > cutoff
                for a in [c.author.email]
            }

            total_commits = len(commits)
            cumulative = 0
            bus_factor = 0
            for author, count in author_commits.most_common():
                cumulative += count
                bus_factor += 1
                if cumulative >= total_commits * 0.8:
                    break

            commits_last_6mo = len([
                c for c in commits
                if c.author_date > datetime.now() - timedelta(days=180)
            ])
            commits_per_week = commits_last_6mo / 26 if repo_age_days >= 180 else 0

            result = {
                "unique_authors": len(all_authors),
                "active_authors": len(active_authors),
                "bus_factor": bus_factor,
                "commit_frequency_per_week": round(commits_per_week, 2),
                "repo_age_days": repo_age_days,
                "is_solo": bus_factor == 1,
                "total_commits": total_commits,
            }

            return result

        except Exception as e:
            logger.warning(f"Error profiling team: {e}")
            return self._default_team_profile()

    def _default_team_profile(self) -> dict[str, Any]:
        """Return default team profile when git mining fails."""
        return {
            "unique_authors": 1,
            "active_authors": 1,
            "bus_factor": 1,
            "commit_frequency_per_week": 0,
            "repo_age_days": 365,
            "is_solo": True,
            "total_commits": 0,
        }

    def get_stack_specific_rates(self, tech_stack: dict) -> dict[str, Any]:
        """Search for technology-specific rates.
        
        Args:
            tech_stack: Tech stack from detect_tech_stack
            
        Returns:
            Rates for each debt category
        """
        cache_key = self._cache.make_key("stack_rates", tech_stack.get("primary_language", "python"))

        if self._cache.is_fresh(cache_key, "repo_profile"):
            cached = self._cache.get(cache_key, "repo_profile")
            if cached and "rates" in cached:
                return cached["rates"]

        primary_lang = tech_stack.get("primary_language", "python")
        frameworks = tech_stack.get("frameworks", [])
        ai_libs = tech_stack.get("ai_ml_libraries", [])
        databases = tech_stack.get("databases", [])
        cloud = tech_stack.get("cloud", [])
        infra = tech_stack.get("infra", [])

        def search_rate(tech: str) -> tuple[str, float, dict]:
            result = self._rate_agent.blend_rates(tech, "mid")
            return tech, result["blended_rate"], result

        techs_to_search = [primary_lang.title()]
        if frameworks:
            techs_to_search.append(frameworks[0].title())
        if ai_libs:
            techs_to_search.append(ai_libs[0].title())
        if databases:
            techs_to_search.append(databases[0].title())
        if cloud:
            techs_to_search.append(cloud[0].title())
        if infra:
            techs_to_search.append(infra[0].title())

        techs_to_search = list(set(techs_to_search))[:6]

        all_rates = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(search_rate, tech): tech
                for tech in techs_to_search
            }
            for future in futures:
                try:
                    tech, rate, detail = future.result()
                    all_rates[tech.lower()] = {"rate": rate, "detail": detail}
                except Exception as e:
                    logger.warning(f"Rate search failed: {e}")

        base_rate = all_rates.get(primary_lang.lower(), {}).get("rate", 84.55)

        specialist_premium = 0.0
        if ai_libs or databases or cloud:
            specialist_premium = 0.15
        if ai_libs:
            specialist_premium += 0.10

        rates_by_category = {
            "code_quality": {
                "rate": all_rates.get(frameworks[0].lower() if frameworks else primary_lang.lower(), {}).get("rate", base_rate),
                "technology": frameworks[0] if frameworks else primary_lang.title(),
                "confidence": "medium",
                "sources": 3,
            },
            "security": {
                "rate": max(
                    all_rates.get(f.lower(), {}).get("rate", base_rate)
                    for f in frameworks + cloud if f in all_rates
                ) if (frameworks or cloud) else base_rate * 1.1,
                "technology": cloud[0] if cloud else (frameworks[0] if frameworks else primary_lang.title()),
                "confidence": "medium",
                "sources": 3,
            },
            "ai_ml_debt": {
                "rate": all_rates.get(ai_libs[0].lower(), {}).get("rate", base_rate * 1.2) if ai_libs else base_rate * 1.2,
                "technology": ai_libs[0] if ai_libs else "AI/ML",
                "confidence": "low",
                "sources": 2,
            },
            "database_debt": {
                "rate": all_rates.get(databases[0].lower(), {}).get("rate", base_rate) if databases else base_rate,
                "technology": databases[0] if databases else "Database",
                "confidence": "low",
                "sources": 2,
            },
            "documentation": {
                "rate": self._rate_agent.get_rate(primary_lang.title(), "junior"),
                "technology": primary_lang.title(),
                "confidence": "high",
                "sources": 4,
            },
            "test_debt": {
                "rate": self._rate_agent.get_rate(primary_lang.title(), "mid"),
                "technology": primary_lang.title(),
                "confidence": "high",
                "sources": 4,
            },
        }

        result = {
            "rates_by_category": rates_by_category,
            "all_rates_searched": {k: v["rate"] for k, v in all_rates.items()},
            "uses_ai": tech_stack.get("uses_ai", False),
            "specialist_premium_pct": specialist_premium * 100,
        }

        return result

    def calculate_multipliers(self, profile: dict) -> dict[str, Any]:
        """Calculate repository-specific cost multipliers.
        
        Args:
            profile: Combined profile from detect_tech_stack and profile_team
            
        Returns:
            Multipliers for each factor and combined
        """
        team = profile.get("team", {})
        tech = profile.get("tech_stack", {})
        ai_det = profile.get("ai_detection", {})

        bus_factor = team.get("bus_factor", 10)
        if bus_factor == 1:
            bus_multiplier = 2.0
        elif bus_factor == 2:
            bus_multiplier = 1.5
        elif bus_factor <= 4:
            bus_multiplier = 1.2
        else:
            bus_multiplier = 1.0

        repo_age = team.get("repo_age_days", 365)
        if repo_age > 2000:
            age_multiplier = 1.3
        elif repo_age > 1000:
            age_multiplier = 1.1
        elif repo_age < 365:
            age_multiplier = 0.9
        else:
            age_multiplier = 1.0

        team_size = team.get("unique_authors", 1)
        if team_size == 1:
            size_multiplier = 1.5
        elif team_size <= 3:
            size_multiplier = 1.2
        elif team_size <= 10:
            size_multiplier = 1.0
        else:
            size_multiplier = 0.9

        uses_ai = tech.get("uses_ai", False)
        has_tests = tech.get("has_tests", False)
        ai_files = ai_det.get("total_suspected", 0)
        total_files = ai_det.get("total_suspected", 0)

        if uses_ai and not has_tests:
            ai_multiplier = 1.4
        elif uses_ai:
            ai_multiplier = 1.1
        else:
            ai_multiplier = 1.0

        test_multiplier = 1.3 if not has_tests else 1.0

        combined = (
            bus_multiplier
            * age_multiplier
            * size_multiplier
            * ai_multiplier
            * test_multiplier
        )
        
        combined = min(combined, 1.8)

        return {
            "bus_factor_multiplier": bus_multiplier,
            "repo_age_multiplier": age_multiplier,
            "team_size_multiplier": size_multiplier,
            "ai_code_multiplier": ai_multiplier,
            "no_tests_multiplier": test_multiplier,
            "combined_multiplier": round(combined, 3),
            "bus_factor": bus_factor,
            "repo_age_days": repo_age,
            "team_size": team_size,
            "uses_ai": uses_ai,
            "has_tests": has_tests,
        }

    def detect_ai_generated_code(self, repo_path: str) -> dict[str, Any]:
        """Detect suspected AI-generated code files.
        
        Args:
            repo_path: Path to repository
            
        Returns:
            AI detection results with suspected files
        """
        cache_key = self._cache.make_key("ai_detection", repo_path)

        if self._cache.is_fresh(cache_key, "repo_profile"):
            cached = self._cache.get(cache_key, "repo_profile")
            if cached and "ai_detection" in cached:
                return cached["ai_detection"]

        suspected_files = []
        total_lines = 0

        try:
            repo = Repository(repo_path, num_workers=1)
            file_commits: dict[str, dict] = {}

            for commit in repo.traverse_commits():
                for modified in commit.modified_files:
                    path = modified.new_path or modified.old_path
                    if not path or not path.endswith(".py"):
                        continue
                    if any(skip in path for skip in SKIP_DIRS):
                        continue

                    if path not in file_commits:
                        file_commits[path] = {
                            "commit_count": 0,
                            "added_lines": 0,
                            "has_tests": False,
                            "commit_lines": {},
                        }

                    fc = file_commits[path]
                    fc["commit_count"] += 1
                    added = modified.added_lines if hasattr(modified, "added_lines") else 0
                    fc["added_lines"] += added

                    if commit.author_date:
                        fc["commit_lines"][commit.author_date] = added

            for file_path, fc in file_commits.items():
                signals = 0
                signal_details = []

                if len(fc["commit_lines"]) == 1:
                    largest_commit = max(fc["commit_lines"].values())
                    if largest_commit > 150:
                        signals += 1
                        signal_details.append("Single large commit")

                if fc["added_lines"] > 100:
                    func_count = self._count_functions(os.path.join(repo_path, file_path))
                    if func_count > 5:
                        has_docstrings = self._check_docstrings(os.path.join(repo_path, file_path))
                        if not has_docstrings:
                            signals += 1
                            signal_details.append("No docstrings")

                generic_pct = self._check_generic_names(os.path.join(repo_path, file_path))
                if generic_pct > 0.4:
                    signals += 1
                    signal_details.append(f"Generic names: {generic_pct:.0%}")

                if fc["added_lines"] > 300:
                    try_complex = self._check_try_except(os.path.join(repo_path, file_path))
                    if not try_complex:
                        signals += 1
                        signal_details.append("No error handling")

                ai_prob = min(1.0, signals / 4)

                if ai_prob > 0.3:
                    suspected_files.append({
                        "file": file_path,
                        "probability": round(ai_prob, 2),
                        "signals": signal_details,
                        "lines_added": fc["added_lines"],
                    })
                    total_lines += fc["added_lines"]

        except Exception as e:
            logger.warning(f"AI detection error: {e}")

        suspected_files.sort(key=lambda x: x["probability"], reverse=True)

        recommendation = "Review suspected files for quality issues"
        if len(suspected_files) > 20:
            recommendation = "High AI usage detected - consider code review"
        elif len(suspected_files) == 0:
            recommendation = "No obvious AI-generated code patterns"

        result = {
            "suspected_files": suspected_files[:50],
            "total_suspected": len(suspected_files),
            "total_suspected_lines": total_lines,
            "recommendation": recommendation,
        }

        return result

    def _count_functions(self, file_path: str) -> int:
        """Count functions in a Python file."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                tree = ast.parse(f.read(), filename=file_path)
            return sum(
                1 for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
        except Exception:
            return 0

    def _check_docstrings(self, file_path: str) -> bool:
        """Check if file has proper docstrings."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                tree = ast.parse(f.read(), filename=file_path)
            funcs = [
                n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            if not funcs:
                return False
            with_docs = sum(1 for f in funcs if ast.get_docstring(f))
            return with_docs / len(funcs) > 0.5
        except Exception:
            return True

    def _check_generic_names(self, file_path: str) -> float:
        """Check percentage of generic variable names."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', content)
            if not words:
                return 0.0
            generic = sum(1 for w in words if w in GENERIC_VAR_NAMES)
            return generic / len(words)
        except Exception:
            return 0.0

    def _check_try_except(self, file_path: str) -> bool:
        """Check if code has try/except blocks."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                tree = ast.parse(f.read(), filename=file_path)
            has_try = any(isinstance(n, ast.Try) for n in ast.walk(tree))
            func_count = sum(
                1 for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
            return has_try or func_count == 0
        except Exception:
            return True

    def profile(self, repo_path: str, github_url: str = None) -> dict[str, Any]:
        """Full repository profile combining all analysis.
        
        Args:
            repo_path: Path to repository
            github_url: Optional GitHub URL
            
        Returns:
            Complete profile with all components
        """
        tech_stack = self.detect_tech_stack(repo_path)
        team = self.profile_team(repo_path)
        rates = self.get_stack_specific_rates(tech_stack)
        ai_detection = self.detect_ai_generated_code(repo_path)

        profile = {
            "tech_stack": tech_stack,
            "team": team,
            "rates": rates,
            "ai_detection": ai_detection,
            "github_url": github_url,
            "profiled_at": datetime.now().isoformat(),
        }

        profile["multipliers"] = self.calculate_multipliers(profile)

        cache_key = self._cache.make_key("full_profile", repo_path)
        self._cache.set(cache_key, "repo_profile", profile)

        return profile
