from __future__ import annotations

from dataclasses import dataclass

from ..contracts import AuditReport, Issue, ObjectRef, Severity


@dataclass(frozen=True)
class FormalRuleMetadata:
    article_clause_mapping: str
    remediation: str
    default_confidence: str = 'medium'


@dataclass(frozen=True)
class FormalIssueDetails:
    issue: Issue
    article_clause_mapping: str
    remediation: str
    risk_level: str
    confidence: str


_FORMAL_RULE_METADATA: dict[str, FormalRuleMetadata] = {
    'wire.floating_endpoints': FormalRuleMetadata(
        article_clause_mapping='SF-EL-001 导线连续性与端点闭合',
        remediation='复核悬空端点坐标，补齐缺失连线或设备端子，并在修正后重新执行审图。',
        default_confidence='high',
    ),
    'device.missing_label': FormalRuleMetadata(
        article_clause_mapping='SF-EL-002 设备标注完整性',
        remediation='为设备补充清晰文本标注，或调整文字与设备的空间对应关系。',
    ),
    'device.duplicate_label': FormalRuleMetadata(
        article_clause_mapping='SF-EL-003 设备唯一标识',
        remediation='核对重复标识设备的命名规则，确保同一图纸内唯一编号对应唯一对象。',
        default_confidence='high',
    ),
    'device.label_pattern_invalid': FormalRuleMetadata(
        article_clause_mapping='SF-EL-004 设备标识命名规则',
        remediation='按设备类别修正标签格式，使设备编号、容量或柜位命名符合既有出图约定。',
    ),
    'electrical.component_missing_terminals': FormalRuleMetadata(
        article_clause_mapping='SF-EL-005 电气组件端子完整性',
        remediation='补齐组件端子定义或修正构件识别结果，确保关键组件具备可追踪的端子集合。',
        default_confidence='high',
    ),
    'electrical.component_unconnected': FormalRuleMetadata(
        article_clause_mapping='SF-EL-006 电气组件落网完整性',
        remediation='检查组件端子是否接入有效网络，必要时补画连接关系或修正端子锚点。',
        default_confidence='high',
    ),
    'electrical.transformer_same_net': FormalRuleMetadata(
        article_clause_mapping='SF-EL-007 变压器双侧网络隔离',
        remediation='复核变压器高低压侧端子落网关系，避免同网短接或端子识别串网。',
        default_confidence='high',
    ),
    'electrical.switch_same_net': FormalRuleMetadata(
        article_clause_mapping='SF-EL-008 开关双端网络隔离',
        remediation='核查开关两侧端子和导线连接，避免同网落点导致开关两侧失去隔离语义。',
        default_confidence='high',
    ),
    'electrical.switchgear_role_connection': FormalRuleMetadata(
        article_clause_mapping='SF-EL-009 开关柜角色连接合理性',
        remediation='结合柜体角色复核上游、下游及母线侧连接对象，补足缺失的柜内或外部关联。',
    ),
    'electrical.switchgear_feed_chain': FormalRuleMetadata(
        article_clause_mapping='SF-EL-010 进出线柜母线链路完整性',
        remediation='检查进线柜、出线柜与母线或联络柜之间的链路表达，补齐断开的供电链路。',
    ),
    'electrical.tie_switchgear_dual_side': FormalRuleMetadata(
        article_clause_mapping='SF-EL-011 联络柜双侧独立接入',
        remediation='确保联络柜同时接入两侧独立网络对象，并明确双侧联络关系。',
    ),
    'electrical.incoming_transformer_busbar_direction': FormalRuleMetadata(
        article_clause_mapping='SF-EL-012 进线柜变压器侧与母线侧方向一致性',
        remediation='调整进线柜端子布局或连接表达，使变压器侧与母线侧分置于相对两侧。',
        default_confidence='high',
    ),
    'electrical.tie_busbar_segment_consistency': FormalRuleMetadata(
        article_clause_mapping='SF-EL-013 联络柜两侧母线分段独立性',
        remediation='补充或修正两侧母线分段标识，确保联络柜两侧母线具备清晰且互不混淆的段别。',
        default_confidence='high',
    ),
    'electrical.busbar_underconnected': FormalRuleMetadata(
        article_clause_mapping='SF-EL-014 母线连接数量下限',
        remediation='检查母线与柜体、变压器或馈线的连接数量，补齐漏接或误删的端子关联。',
    ),
    'electrical.branch_box_insufficient_branches': FormalRuleMetadata(
        article_clause_mapping='SF-EL-015 分支箱有效分支数量',
        remediation='补齐分支箱的分支端或更正端子角色识别，使分支数量满足设计意图。',
    ),
    'electrical.relation_unresolved': FormalRuleMetadata(
        article_clause_mapping='SF-EL-016 未闭合电气关系复核',
        remediation='针对未闭合的组件关系、端子或锚点补充连接证据，并复核相关构件识别。',
    ),
    'topo.terminal_unconnected': FormalRuleMetadata(
        article_clause_mapping='SF-EL-006 电气组件落网完整性',
        remediation='检查端子是否被正确吸附到网络节点，并补齐缺失连线或端子映射。',
        default_confidence='high',
    ),
    'topo.breaker_same_net': FormalRuleMetadata(
        article_clause_mapping='SF-EL-008 开关双端网络隔离',
        remediation='复核断路器端子落网关系，避免两侧端子被错误并入同一网络。',
        default_confidence='high',
    ),
    'cad.parse_failed': FormalRuleMetadata(
        article_clause_mapping='SF-EL-900 CAD 解析前置条件',
        remediation='确认源文件格式、转换工具与解析后端可用，必要时先完成 DWG->DXF 转换再复跑。',
        default_confidence='high',
    ),
    'audit.internal_error': FormalRuleMetadata(
        article_clause_mapping='SF-EL-901 审图运行完整性',
        remediation='结合报错信息排查运行环境或输入数据异常，修复后重新生成正式报告。',
        default_confidence='medium',
    ),
}

_RISK_BY_SEVERITY = {
    Severity.ERROR: 'high',
    Severity.WARNING: 'medium',
    Severity.INFO: 'low',
}

_CONFIDENCE_LABELS = ('low', 'medium', 'high')
_CONFIDENCE_SCORES = {label: index for index, label in enumerate(_CONFIDENCE_LABELS)}


def build_formal_issue_details(report: AuditReport) -> list[FormalIssueDetails]:
    drawing_type = _drawing_type_from_report(report)
    details: list[FormalIssueDetails] = []
    for issue in report.issues:
        metadata = _FORMAL_RULE_METADATA.get(issue.rule_id, _fallback_metadata(issue.rule_id))
        details.append(
            FormalIssueDetails(
                issue=issue,
                article_clause_mapping=metadata.article_clause_mapping,
                remediation=metadata.remediation,
                risk_level=_RISK_BY_SEVERITY.get(issue.severity, 'medium'),
                confidence=_derive_confidence(issue, drawing_type=drawing_type, default=metadata.default_confidence),
            )
        )
    return details


def _fallback_metadata(rule_id: str) -> FormalRuleMetadata:
    return FormalRuleMetadata(
        article_clause_mapping=f'SF-EL-999 未分类审图条款 ({rule_id})',
        remediation='结合命中的对象引用复核图纸与建模结果，并在修正后重新生成报告。',
        default_confidence='medium',
    )


def _drawing_type_from_report(report: AuditReport) -> str | None:
    summary = report.summary if isinstance(report.summary, dict) else {}
    classification = summary.get('classification')
    if isinstance(classification, dict):
        drawing_type = classification.get('drawing_type')
        if isinstance(drawing_type, str) and drawing_type:
            return drawing_type
    return None


def _derive_confidence(issue: Issue, *, drawing_type: str | None, default: str) -> str:
    score = _CONFIDENCE_SCORES.get(default, _CONFIDENCE_SCORES['medium'])
    if issue.rule_id == 'cad.parse_failed':
        return 'high'
    if issue.rule_id == 'audit.internal_error':
        return 'medium'

    coordinate_refs = sum(1 for ref in issue.refs if _has_coordinates(ref))
    if len(issue.refs) >= 2:
        score = max(score, _CONFIDENCE_SCORES['high' if coordinate_refs else 'medium'])
    elif coordinate_refs:
        score = max(score, _CONFIDENCE_SCORES['medium'])
    elif not issue.refs:
        score = max(_CONFIDENCE_SCORES['low'], score - 1)

    if drawing_type in {'layout_or_installation', 'other'} and score > _CONFIDENCE_SCORES['low']:
        score -= 1
    return _CONFIDENCE_LABELS[score]


def _has_coordinates(ref: ObjectRef) -> bool:
    extra = ref.extra or {}
    return extra.get('x') is not None and extra.get('y') is not None
