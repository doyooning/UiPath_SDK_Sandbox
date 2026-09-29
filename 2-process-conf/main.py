"""PostAgent — velog 소개글 수정 / 게시물 업로드 자동화 에이전트.

자연어 요청을 받아 LLM 으로 작업 계획(소개글 문구, 게시물 초안)을 세우고,
Orchestrator 에 배포된 velog자동화 패키지의 두 프로세스를 순서대로 호출한다.

    velog_EditIntro  (EditIntro.xaml)  in_IntroText
    velog_WritePost  (WritePost.xaml)  in_Title, in_Body, in_Tags, in_Description, in_IsPrivate

프로세스 호출은 interrupt(InvokeProcess(...)) 로 한다. 에이전트 잡은 RPA 잡이
끝날 때까지 suspend 되었다가 결과를 받아 재개된다. RPA 잡이 실패하면 런타임이
예외를 올려 에이전트 잡도 실패로 끝난다(뒤 단계는 실행되지 않는다).

    uip codedagent run agent '{"request": "소개글을 ...로 바꾸고 ... 주제로 글 올려줘"}'
    uip codedagent run agent '{"request": "...", "dry_run": true}'   # 계획만 확인
"""

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field
from uipath.platform.common import InvokeProcess
from uipath_langchain.chat import UiPathChat


# 호출 대상 프로세스. bindings.json 에 같은 값으로 등록되어 있어
# 배포 후 Orchestrator 에서 프로세스/폴더를 바꿔 끼울 수 있다.
PROCESS_FOLDER = "dynii1923@gmail.com's workspace"
EDIT_INTRO_PROCESS = "velog_EditIntro"
WRITE_POST_PROCESS = "velog_WritePost"


class PostDraft(BaseModel):
    title: str = Field(description="게시물 제목")
    body: str = Field(description="게시물 본문 (Markdown)")
    tags: list[str] = Field(default_factory=list, description="태그 목록")
    description: str = Field(default="", description="포스트 소개 문구 (150자 이내)")
    is_private: bool = Field(default=False, description="비공개 여부")


# 1단계(요청 해석) 구조화 출력. 본문처럼 긴 생성과 작업 분류를 한 번에 시키면
# 모델이 게시물 작업을 통째로 건너뛰는 경우가 있어 해석과 초안 작성을 나눈다.
class TaskPlan(BaseModel):
    edit_intro: bool = Field(description="요청에 소개글 수정이 포함되면 true")
    intro_text: str = Field(description="새 velog 소개글. edit_intro 가 false 면 빈 문자열")
    write_post: bool = Field(description="요청에 게시물 작성/업로드가 포함되면 true")
    post_request: str = Field(
        description="게시물 관련 요구사항(주제, 제목, 본문, 태그, 공개 여부 등)을 요청에서 그대로 발췌. "
        "write_post 가 false 면 빈 문자열"
    )


class Input(BaseModel):
    request: str = Field(description="velog 작업 요청 (소개글 수정 / 게시물 업로드, 자연어)")
    dry_run: bool = Field(
        default=False,
        description="True 면 계획만 세우고 velog 프로세스는 실행하지 않는다",
    )


class State(BaseModel):
    request: str
    dry_run: bool = False

    intro_text: str | None = None
    post_request: str | None = None
    post: PostDraft | None = None

    # skipped | planned | success
    intro_status: str = "skipped"
    post_status: str = "skipped"


class Output(BaseModel):
    summary: str = Field(description="처리 결과 요약")
    intro_status: str = Field(description="소개글 수정 결과: skipped | planned | success")
    post_status: str = Field(description="게시물 업로드 결과: skipped | planned | success")
    intro_text: str | None = Field(default=None, description="적용(또는 계획)한 소개글")
    post_title: str | None = Field(default=None, description="업로드(또는 계획)한 게시물 제목")


PLAN_PROMPT = """당신은 velog 블로그 운영을 돕는 어시스턴트다.
사용자 요청에 다음 두 작업이 각각 포함되어 있는지 판단한다. 두 작업은 서로 독립적이며,
한 요청에 둘 다 있으면 둘 다 true 로 표시한다.

1. 소개글 수정 — "소개글", "자기소개", "프로필 소개" 를 바꾸라는 표현
   edit_intro=true 로 두고 intro_text 에 새 소개글을 쓴다.
   사용자가 문구를 그대로 지정했으면 그대로 쓰고, 방향만 줬으면 짧고 자연스럽게 작성한다.
2. 게시물 업로드 — 글/포스트/게시물을 올려/써/작성/업로드/발행하라는 표현
   write_post=true 로 두고 post_request 에 게시물 관련 요구사항을 발췌한다.
   게시물 본문은 여기서 쓰지 않는다.

예시: 소개글을 "안녕하세요"로 바꾸고, Docker 입문 글을 태그 docker로 올려줘
→ edit_intro=true, intro_text="안녕하세요", write_post=true,
  post_request="Docker 입문 글을 태그 docker로 올려줘"
"""

DRAFT_PROMPT = """당신은 velog 기술 블로그 글을 쓰는 작가다.
요구사항에 맞는 게시물을 작성한다.

- title: 간결한 제목. 사용자가 제목을 지정했으면 그대로 쓴다.
- body: Markdown 본문. 사용자가 본문을 주면 그대로 쓰고, 주제만 주면 직접 작성한다.
  제목을 본문 첫 줄에 반복하지 않는다.
- tags: 1~5개, 공백 없는 짧은 단어. 쉼표(,)를 포함하지 않는다. 지정된 태그가 있으면 그대로 쓴다.
- description: 목록에 노출될 한두 문장 소개 (150자 이내)
- is_private: 사용자가 비공개를 요청한 경우에만 true"""


def _as_model(result, model: type[BaseModel]):
    # with_structured_output 은 버전에 따라 dict 를 돌려주기도 한다
    return result if isinstance(result, model) else model.model_validate(result)


async def plan_node(state: State) -> dict:
    # 요청 해석은 흔들리지 않도록 temperature 0
    llm = UiPathChat(model="gpt-4.1-mini-2025-04-14", temperature=0)
    result = await llm.with_structured_output(TaskPlan).ainvoke(
        [SystemMessage(PLAN_PROMPT), HumanMessage(state.request)]
    )
    plan = _as_model(result, TaskPlan)

    intro_text = plan.intro_text.strip() if plan.edit_intro else ""
    post_request = plan.post_request.strip() if plan.write_post else ""
    pending = "planned" if state.dry_run else "skipped"

    return {
        "intro_text": intro_text or None,
        "post_request": post_request or None,
        "intro_status": pending if intro_text else "skipped",
    }


async def draft_post_node(state: State) -> dict:
    llm = UiPathChat(model="gpt-4.1-mini-2025-04-14", temperature=0.7)
    result = await llm.with_structured_output(PostDraft).ainvoke(
        [SystemMessage(DRAFT_PROMPT), HumanMessage(state.post_request)]
    )
    draft = _as_model(result, PostDraft)
    post = draft.model_copy(
        update={
            "title": draft.title.strip(),
            "tags": [t.replace(",", " ").strip() for t in draft.tags if t.strip()],
            "description": draft.description.strip(),
        }
    )
    return {
        "post": post,
        "post_status": "planned" if state.dry_run else "skipped",
    }


def route_after_plan(state: State) -> str:
    if state.post_request:
        return "draft_post"
    return route_to_process(state)


def route_to_process(state: State) -> str:
    if state.dry_run:
        return "respond"
    if state.intro_text:
        return "edit_intro"
    if state.post:
        return "write_post"
    return "respond"


def route_after_intro(state: State) -> str:
    return "write_post" if state.post else "respond"


async def edit_intro_node(state: State) -> dict:
    interrupt(
        InvokeProcess(
            name=EDIT_INTRO_PROCESS,
            process_folder_path=PROCESS_FOLDER,
            input_arguments={"in_IntroText": state.intro_text},
        )
    )
    return {"intro_status": "success"}


async def write_post_node(state: State) -> dict:
    post = state.post
    interrupt(
        InvokeProcess(
            name=WRITE_POST_PROCESS,
            process_folder_path=PROCESS_FOLDER,
            input_arguments={
                "in_Title": post.title,
                "in_Body": post.body,
                # WritePost.xaml 이 쉼표로 split 해서 태그를 하나씩 입력한다
                "in_Tags": ",".join(post.tags),
                "in_Description": post.description,
                "in_IsPrivate": post.is_private,
            },
        )
    )
    return {"post_status": "success"}


async def respond_node(state: State) -> Output:
    lines = []

    if state.intro_status == "success":
        lines.append(f"소개글을 수정했습니다: {state.intro_text}")
    elif state.intro_status == "planned":
        lines.append(f"[dry-run] 소개글 수정 예정: {state.intro_text}")

    if state.post_status == "success":
        visibility = "비공개" if state.post.is_private else "전체 공개"
        lines.append(f"게시물을 업로드했습니다({visibility}): {state.post.title}")
    elif state.post_status == "planned":
        lines.append(f"[dry-run] 게시물 업로드 예정: {state.post.title}")

    if not lines:
        lines.append("요청에서 소개글 수정이나 게시물 업로드 작업을 찾지 못했습니다.")

    return Output(
        summary="\n".join(lines),
        intro_status=state.intro_status,
        post_status=state.post_status,
        intro_text=state.intro_text,
        post_title=state.post.title if state.post else None,
    )


builder = StateGraph(State, input_schema=Input, output_schema=Output)

builder.add_node("plan", plan_node)
builder.add_node("draft_post", draft_post_node)
builder.add_node("edit_intro", edit_intro_node)
builder.add_node("write_post", write_post_node)
builder.add_node("respond", respond_node)

builder.add_edge(START, "plan")
builder.add_conditional_edges(
    "plan", route_after_plan, ["draft_post", "edit_intro", "write_post", "respond"]
)
builder.add_conditional_edges(
    "draft_post", route_to_process, ["edit_intro", "write_post", "respond"]
)
builder.add_conditional_edges("edit_intro", route_after_intro, ["write_post", "respond"])
builder.add_edge("write_post", "respond")
builder.add_edge("respond", END)

graph = builder.compile()
