## Brainstorming Summary: Cross-Repository Clone Similarity for Final-Stage Matching

### Motivation

In observational studies of AI coding assistant adoption, such as studies of Cursor adoption in open-source repositories, a major challenge is constructing a credible control group. Metadata-based matching can identify repositories with similar activity patterns, popularity, maturity, and community size. However, two repositories may look similar in GitHub metadata while having very different source-code structures, complexity, or implementation patterns.

To improve the quality of matching, we propose adding a final-stage source-code similarity check based on cross-repository clone detection.

### Core Idea

The proposed method computes source-code similarity between a treated repository and candidate control repositories before treatment. For a treated repository that adopts Cursor at time (t), each candidate control repository is checked out at the same cutoff time (t), even though the control repository never adopts Cursor. This follows the logic of staggered difference-in-differences: the treated repository’s adoption month defines the before/after cutoff for its matched controls.

Instead of comparing every file in both repositories, the method focuses on a deterministic subset of important source files. This reduces computational cost while still capturing meaningful project-level code similarity.

### Important Distinction

There are two different clone-related concepts:

1. **Within-repository duplicate density**
   This measures how much duplicated code exists inside one repository. It is useful as a code-quality outcome.

2. **Cross-repository clone similarity**
   This measures how similar a treated repository and a candidate control repository are to each other before treatment. This is useful as a matching refinement.

The proposed idea concerns the second concept: cross-repository clone similarity.

### Proposed Pipeline

The matching process can be organized as a cost-aware, multi-stage pipeline.

#### Stage 1: Activity-Based Matching

First, identify broadly similar candidate controls using pre-adoption repository metadata and activity history, such as:

* repository age
* active users
* stars
* forks
* releases
* pull requests
* issues
* comments
* total GitHub events
* primary programming language

This stage captures whether repositories had similar popularity, maturity, and development trajectories before treatment.

#### Stage 2: Cheap Source-Code Metric Matching

Second, refine the candidate controls using inexpensive pre-adoption code metrics, such as:

* lines of code
* number of source files
* number of directories
* average file size
* code complexity
* static-analysis warning density
* test file ratio
* dependency count
* language composition

This stage helps ensure that candidate controls are not only socially and operationally similar, but also similar in codebase size and quality state.

#### Stage 3: Cross-Repository Clone Similarity

Finally, among the remaining candidate controls, compute source-code similarity between each treated-control pair using clone detection on selected important files.

For each treated repository (A) and candidate control repository (A'):

1. Identify the treated repository’s Cursor adoption cutoff.
2. Checkout both (A) and (A') at the treated repository’s pre-adoption cutoff.
3. Select important source files from both repositories using only pre-adoption information.
4. Run a clone detector on the combined selected file set.
5. Measure how many clone classes contain clone instances from both repositories.
6. Prefer candidate controls with higher cross-repository clone similarity, while avoiding extremely high similarity that may indicate forks, mirrors, templates, or copied projects.

### Important File Selection

To reduce computational cost, clone detection does not need to be run on the entire repository. Instead, we can select important files using deterministic pre-adoption criteria, such as:

* most frequently changed files
* files with highest pre-adoption churn
* largest source files
* most complex files
* files central in the import or dependency graph
* main entry-point files
* core API, service, router, model, or controller files
* important test files, if test similarity is relevant

This makes the method more scalable than whole-repository clone detection.

### Similarity Score

A simple score is the proportion of clone classes that contain instances from both repositories:

[
\text{Mixed Clone Class Ratio} =
\frac{# \text{clone classes containing instances from both repos}}
{# \text{all clone classes}}
]

However, a more robust score should account for clone size and repository size:

[
\text{Shared Clone Coverage} =
\frac{2 \times \text{shared cloned LOC}}
{\text{selected LOC in treated repo} + \text{selected LOC in control repo}}
]

The intuition is:

> The more clone classes, or cloned lines, are shared across the treated and candidate control repositories before treatment, the more similar the two repositories are at the source-code level.

### Why This Is Useful

This final-stage clone-based similarity check can improve matching quality by capturing similarity that metadata cannot detect. For example, two repositories may have similar stars, pull requests, and contributor counts, but one may be a small plugin and the other a large framework. Source-code similarity can help avoid such mismatches.

It can also reduce the risk that post-adoption differences in complexity or quality are caused by pre-existing codebase differences rather than Cursor adoption.

### Practical Considerations

Whole-repository clone detection can be computationally expensive, especially with tools such as NiCad, SourcererCC, or LLM-based clone detectors. Therefore, clone-based similarity should not be used as the first-stage matching method. It is more practical as a final-stage refinement after metadata and cheap code-metric filtering have already reduced the candidate pool.

For example, for each treated repository, we may first reduce thousands of possible controls to 20 or 30 candidates, then run cross-repository clone detection only on those candidates.

### Risks and Controls

Several risks should be addressed:

* Shared boilerplate may inflate similarity.
* Generated, vendored, minified, build, and dependency files should be excluded.
* Template-derived repositories may appear highly similar but may not be good independent controls.
* Very high similarity may indicate forks, mirrors, or copied projects.
* Test code and production code should possibly be analyzed separately.
* Language-specific clone detection issues should be considered.
* All clone similarity metrics must be computed only using pre-adoption snapshots.

### Suggested Use in Research Design

This method should be framed as a matching refinement, not as a replacement for difference-in-differences. The causal estimate would still come from the DiD design. Cross-repository clone similarity would improve the credibility of the matched control group by ensuring that treated and control repositories were similar not only in activity history, but also in pre-treatment source-code structure.

### Summary

The proposed extension is a cost-aware final-stage matching method. It first uses activity and metadata to identify broadly similar controls, then uses cheap pre-adoption code metrics to refine the candidate pool, and finally uses cross-repository clone similarity on important source files to select controls with stronger source-code similarity. This approach may improve control-group quality while avoiding the high computational cost of full repository-level clone detection across a large candidate pool.
