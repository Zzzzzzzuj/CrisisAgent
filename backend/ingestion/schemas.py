from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class RawSentimentItem:
    item_id: str
    source_name: str
    source_url: str
    title: str
    content: str
    published_at: str
    company: str
    fact_status: str = "unverified"
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedSentimentItem:
    item_id: str
    source_name: str
    source_url: str
    title: str
    normalized_text: str
    published_at: str
    company: str
    fact_status: str
    url_hash: str
    title_hash: str
    content_hash: str


@dataclass(frozen=True)
class ClusteredCrisisEvent:
    cluster_id: str
    company: str
    event: str
    source_items: list[str]
    source_count: int
    first_published_at: str
    last_published_at: str
    event_status: str
    fact_status: str
    risk_level: str
    public_emotion: str
    human_review_required: bool
    event_fingerprint: str

    def to_dict(self) -> dict:
        return asdict(self)
