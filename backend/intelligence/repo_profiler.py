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

    def profile_team(self, repo_path: str) -> dict:
        import logging
        logger = logging.getLogger(__name__)
        
        # Verify repo path exists and has git history
        git_dir = os.path.join(repo_path, '.git')
        if not os.path.exists(git_dir):
            logger.warning(f"No .git found at {repo_path}")
            return self._default_team_profile()
        
        logger.info(f"Profiling team for repo at: {repo_path}")
        
        try:
            from pydriller import Repository
            
            commits = list(Repository(repo_path).traverse_commits())
            logger.info(f"Found {len(commits)} total commits")
            
            if not commits:
                return self._default_team_profile()
            
            # All unique authors ever
            all_emails = set(c.author.email for c in commits 
                            if c.author and c.author.email)
            
            # Active authors = last 90 days
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(days=90)
            active_emails = set(
                c.author.email for c in commits
                if c.author and c.author.email 
                and c.author_date and c.author_date.replace(tzinfo=None) > cutoff
            )
            
            # Repo age
            first_commit = commits[0]
            last_commit = commits[-1]
            repo_age_days = (
                last_commit.author_date - first_commit.author_date
            ).days if first_commit.author_date and last_commit.author_date else 365
            
            # Bus factor: authors covering 80% of commits
            from collections import Counter
            author_commits = Counter(
                c.author.email for c in commits if c.author
            )
            total_commits = len(commits)
            sorted_authors = author_commits.most_common()
            
            cumulative = 0
            bus_factor = 0
            for author, count in sorted_authors:
                cumulative += count
                bus_factor += 1
                if cumulative / total_commits >= 0.8:
                    break
            
            team_size = len(all_emails)
            logger.info(f"Team: {team_size} total, {len(active_emails)} active, "
                       f"bus_factor={bus_factor}, age={repo_age_days}d")
            
            return {
                "estimated_team_size": team_size,
                "unique_authors": team_size,
                "team_size": team_size,
                "active_contributors": len(active_emails),
                "active_authors": len(active_emails),
                "bus_factor": bus_factor,
                "repo_age_days": repo_age_days,
                "total_commits": total_commits,
                "is_solo": bus_factor == 1,
                "commit_frequency": round(total_commits / max(repo_age_days/7, 1), 1)
            }
            
        except Exception as e:
            logger.error(f"Team profiling failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._default_team_profile()

    def _default_team_profile(self) -> dict:
        return {
            "estimated_team_size": 1,
            "unique_authors": 1,
            "team_size": 1,
            "active_contributors": 1,
            "active_authors": 1,
            "bus_factor": 1,
            "repo_age_days": 365,
            "total_commits": 0,
            "is_solo": True,
            "commit_frequency": 1.0
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

    def calculate_multipliers(self, team_profile: dict) -> dict:
        repo_age_days = team_profile.get('repo_age_days', 365)
        bus_factor = team_profile.get('bus_factor', 1)
        team_size = team_profile.get('estimated_team_size', 1)
        
        # Repo age multiplier
        if repo_age_days > 3650:      # > 10 years
            repo_age_mult = 1.4
        elif repo_age_days > 2000:    # > 5.5 years
            repo_age_mult = 1.3
        elif repo_age_days > 1000:    # > 2.7 years
            repo_age_mult = 1.1
        elif repo_age_days < 180:     # < 6 months (new project)
            repo_age_mult = 0.8
        else:
            repo_age_mult = 1.0
        
        # Bus factor multiplier
        if bus_factor == 1:
            bus_factor_mult = 2.0
        elif bus_factor == 2:
            bus_factor_mult = 1.5
        elif bus_factor <= 4:
            bus_factor_mult = 1.2
        else:
            bus_factor_mult = 1.0
        
        # Team size multiplier
        if team_size == 1:
            team_size_mult = 1.5
        elif team_size <= 3:
            team_size_mult = 1.2
        elif team_size <= 10:
            team_size_mult = 1.0
        else:
            team_size_mult = 0.9   # larger teams = better knowledge sharing
        
        combined = round(repo_age_mult * bus_factor_mult * team_size_mult, 2)
        
        return {
            "repo_age_multiplier": repo_age_mult,
            "bus_factor_multiplier": bus_factor_mult,
            "team_size_multiplier": team_size_mult,
            "ai_code_multiplier": 1.0,
            "no_tests_multiplier": 1.0,
            "combined_multiplier": combined,
            "repo_age_days": repo_age_days,
            "bus_factor": bus_factor,
            "team_size": team_size,
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

        profile["multipliers"] = self.calculate_multipliers(team)

        cache_key = self._cache.make_key("full_profile", repo_path)
        self._cache.set(cache_key, "repo_profile", profile)

        return profile
