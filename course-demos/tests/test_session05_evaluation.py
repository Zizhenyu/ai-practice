from conftest import load_session

judge = load_session("session-05-evaluation", "judge")
compare_prompts = load_session("session-05-evaluation", "compare_prompts")


def test_token_overlap_identical_text_is_1():
    assert judge.token_overlap("hello world", "hello world") == 1.0


def test_token_overlap_no_shared_tokens_is_0():
    assert judge.token_overlap("abc def", "xyz uvw") == 0.0


def test_judge_point_mock_uses_token_overlap_threshold():
    assert judge.judge_point("the rollback finished at 09:58 with metrics recovered",
                              "rollback finished at 09:58 metrics recovered") is True
    assert judge.judge_point("totally unrelated text", "rollback finished at 09:58") is False


def test_evaluate_default_summary_covers_all_ground_truth_points(capsys):
    score = judge.evaluate(judge.DEFAULT_SUMMARY)
    assert score == 1.0


def test_structured_prompt_scores_higher_than_lazy_prompt(capsys):
    v1_score = compare_prompts.evaluate(compare_prompts.MOCK_V1)
    v2_score = compare_prompts.evaluate(compare_prompts.MOCK_V2)
    assert v2_score > v1_score
