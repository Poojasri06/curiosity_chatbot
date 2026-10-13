"""Answers to questions about using the website (accounts, certificates, contact), with direct links.

These are fixed answers, not AI text, so they are always correct and always give the same link.
Page paths come from the LMS routes (routes/tenant.php). If a path changes, edit it here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .schemas import Source


@dataclass(frozen=True)
class HelpTopic:
    name: str
    pattern: re.Pattern
    answer: str
    link_title: str
    path: str


def _topic(name: str, pattern: str, answer: str, link_title: str, path: str) -> HelpTopic:
    return HelpTopic(name, re.compile(pattern, re.I), answer, link_title, path)


TOPICS = [
    _topic(
        "forgot_password",
        r"forgot.*password|reset.*password|password.*(reset|forgot|lost)|can.?t (log ?in|sign ?in)|cannot (log ?in|sign ?in)",
        "No problem. Open the sign-in page and choose Forgot password, then follow the steps to set a new one.",
        "Open the sign-in page",
        "/login",
    ),
    _topic(
        "create_account",
        r"(create|make|open|start|get|set ?up).{0,20}(account|profile)|sign ?up|register(?!.*\bfor\b)|registration|join (the )?(platform|site|curiosity)|new (user|account)",
        "You can create your free account on the sign-up page. It only takes a minute.",
        "Create your account",
        "/register",
    ),
    _topic(
        "login",
        r"log ?in|sign ?in|login page",
        "You can sign in from the sign-in page.",
        "Open the sign-in page",
        "/login",
    ),
    _topic(
        "verify_certificate",
        r"verify.*certificate|certificate.*(verif|valid|check|authentic)|check.*certificate",
        "You can verify any certificate with its certificate number on the verification page.",
        "Verify a certificate",
        "/certificate-verification",
    ),
    _topic(
        "my_courses",
        r"my courses|my learning|where.*(my|enrolled|started).*course|continue.*(course|learning)|my dashboard|student dashboard",
        "After you sign in, your enrolled courses are in My Courses.",
        "Open My Courses",
        "/my-courses",
    ),
    _topic(
        "become_instructor",
        r"become.*(instructor|teacher|trainer)|teach (on|here|a course)|(instructor|teacher).*(apply|join|sign ?up)|(apply|join).*(instructor|teacher)",
        "Great that you want to teach. You can apply on the become an instructor page.",
        "Become an instructor",
        "/become-instructor",
    ),
    _topic(
        "contact",
        r"contact|support|help ?desk|customer care|talk to (a |some)?(human|person|someone|agent)|reach (you|us|the team)|email (you|us)|phone number|complain|report (a )?(problem|issue|bug)",
        "You can reach the team through the contact page, and they will get back to you.",
        "Contact us",
        "/contact-us",
    ),
    _topic(
        "about",
        r"about (you|us|curiosity|this (site|platform|website))|who (are|is) (you|curiosity)|what is curiosity",
        "You can read about Curiosity and who is behind it on the about page.",
        "About Curiosity",
        "/about-us",
    ),
    _topic(
        "all_courses",
        r"all courses page|(course|courses) (page|list page)|where.*(find|see|browse).*courses",
        "Every course is on the courses page, where you can search and filter. I can also list them here by department if you like.",
        "Browse all courses",
        "/courses",
    ),
    _topic(
        "privacy",
        r"privacy|personal data|data policy",
        "You can read how personal data is handled on the privacy page.",
        "Privacy policy",
        "/privacy",
    ),
]


def find_topic(message: str) -> HelpTopic | None:
    for topic in TOPICS:
        if topic.pattern.search(message):
            return topic
    return None


def help_answer(topic: HelpTopic, base_url: str) -> tuple[str, list[Source]]:
    return topic.answer, [Source(title=topic.link_title, url=base_url + topic.path)]
