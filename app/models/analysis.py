"""Explicit analysis requests; the model never chooses or executes code."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

TestName = Literal[
    "descriptive",
    "pearson",
    "spearman",
    "chi_square",
    "independent_t",
    "paired_t",
    "anova",
    "mann_whitney",
    "wilcoxon",
    "kruskal_wallis",
    "linear_regression",
    "logistic_regression",
]


class AnalysisSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    test: TestName
    columns: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def dimensions(self):
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("Analysis columns must be distinct")
        if (
            self.test not in {"descriptive", "linear_regression", "logistic_regression"}
            and len(self.columns) != 2
        ):
            raise ValueError("This test requires exactly two columns")
        if self.test.endswith("regression") and len(self.columns) < 2:
            raise ValueError("Regression requires outcome followed by predictors")
        return self


class AnalysisPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analyses: list[AnalysisSpec] = Field(default_factory=list, max_length=30)
    correction: Literal["BH", "holm", "bonferroni"] = "BH"


class Interpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    explanation: str = Field(min_length=1, max_length=1000)
    cautions: list[str] = Field(default_factory=list, max_length=8)
