"""
Complete Rule-to-Category Mapping for Static Analysis Warnings
====================================================================
For studying AI Coding Assistant (Cursor) impact on code quality.

Categories designed to test hypotheses about AI-generated code characteristics.
"""

# ============================================================================
# MAIN MAPPING: rule -> category
# ============================================================================

RULE_TO_CATEGORY = {
    # =========================================================================
    # 1. CODE HYGIENE - Leftover artifacts, cleanup issues
    # Hypothesis: AI leaves scaffolding, TODOs, commented alternatives
    # Expected: ↑ increase post-adoption
    # =========================================================================
    # Commented code (S125)
    "Web:AvoidCommentedOutCodeCheck": "Code Hygiene",
    "css:S125": "Code Hygiene",
    "ipython:S125": "Code Hygiene",
    "java:S125": "Code Hygiene",
    "javascript:S125": "Code Hygiene",
    "php:S125": "Code Hygiene",
    "python:S125": "Code Hygiene",
    "typescript:S125": "Code Hygiene",
    "xml:S125": "Code Hygiene",
    # TODO/FIXME comments (S1134, S1135)
    "Web:S1134": "Code Hygiene",
    "Web:S1135": "Code Hygiene",
    "docker:S1135": "Code Hygiene",
    "go:S1134": "Code Hygiene",
    "go:S1135": "Code Hygiene",
    "ipython:S1135": "Code Hygiene",
    "java:S1134": "Code Hygiene",
    "java:S1135": "Code Hygiene",
    "javascript:S1134": "Code Hygiene",
    "javascript:S1135": "Code Hygiene",
    "kotlin:S1135": "Code Hygiene",
    "kubernetes:S1135": "Code Hygiene",
    "php:S1134": "Code Hygiene",
    "php:S1135": "Code Hygiene",
    "python:S1134": "Code Hygiene",
    "python:S1135": "Code Hygiene",
    "ruby:S1135": "Code Hygiene",
    "terraform:S1135": "Code Hygiene",
    "typescript:S1134": "Code Hygiene",
    "typescript:S1135": "Code Hygiene",
    # Unused imports (S1128)
    "java:S1128": "Code Hygiene",
    "javascript:S1128": "Code Hygiene",
    "kotlin:S1128": "Code Hygiene",
    "typescript:S1128": "Code Hygiene",
    # Unused local variables (S1481)
    "java:S1481": "Code Hygiene",
    "javascript:S1481": "Code Hygiene",
    "kotlin:S1481": "Code Hygiene",
    "php:S1481": "Code Hygiene",
    "python:S1481": "Code Hygiene",
    "ruby:S1481": "Code Hygiene",
    # Unused private fields (S1068)
    "java:S1068": "Code Hygiene",
    "javascript:S1068": "Code Hygiene",
    "php:S1068": "Code Hygiene",
    "typescript:S1068": "Code Hygiene",
    # Unused private methods (S1144)
    "java:S1144": "Code Hygiene",
    "kotlin:S1144": "Code Hygiene",
    "php:S1144": "Code Hygiene",
    "python:S1144": "Code Hygiene",
    # Unused function parameters (S1172)
    "ipython:S1172": "Code Hygiene",
    "java:S1172": "Code Hygiene",
    "kotlin:S1172": "Code Hygiene",
    "php:S1172": "Code Hygiene",
    "python:S1172": "Code Hygiene",
    "ruby:S1172": "Code Hygiene",
    # Useless assignments (S1854)
    "java:S1854": "Code Hygiene",
    "javascript:S1854": "Code Hygiene",
    "php:S1854": "Code Hygiene",
    "python:S1854": "Code Hygiene",
    "typescript:S1854": "Code Hygiene",
    # Redundant jumps (S3626)
    "ipython:S3626": "Code Hygiene",
    "java:S3626": "Code Hygiene",
    "javascript:S3626": "Code Hygiene",
    "php:S3626": "Code Hygiene",
    "python:S3626": "Code Hygiene",
    "typescript:S3626": "Code Hygiene",
    # =========================================================================
    # 2. ACCESSIBILITY - A11y issues
    # Hypothesis: AI training data underrepresents accessibility patterns
    # Expected: ↑ increase or no change
    # =========================================================================
    # HTML/Web accessibility
    "Web:FrameWithoutTitleCheck": "Accessibility",
    "Web:ImgWithoutAltCheck": "Accessibility",
    "Web:MouseEventWithoutKeyboardEquivalentCheck": "Accessibility",
    "Web:PageWithoutTitleCheck": "Accessibility",
    "Web:S4084": "Accessibility",
    "Web:S5254": "Accessibility",
    "Web:S5255": "Accessibility",
    "Web:S5256": "Accessibility",
    "Web:S5257": "Accessibility",
    "Web:S6793": "Accessibility",
    "Web:S6807": "Accessibility",
    "Web:S6819": "Accessibility",
    "Web:S6821": "Accessibility",
    "Web:S6822": "Accessibility",
    "Web:S6825": "Accessibility",
    "Web:S6827": "Accessibility",
    "Web:S6840": "Accessibility",
    "Web:S6841": "Accessibility",
    "Web:S6842": "Accessibility",
    "Web:S6843": "Accessibility",
    "Web:S6844": "Accessibility",
    "Web:S6845": "Accessibility",
    "Web:S6846": "Accessibility",
    "Web:S6847": "Accessibility",
    "Web:S6848": "Accessibility",
    "Web:S6850": "Accessibility",
    "Web:S6851": "Accessibility",
    "Web:S6853": "Accessibility",
    "Web:TableHeaderHasIdOrScopeCheck": "Accessibility",
    # JavaScript accessibility
    "javascript:S1082": "Accessibility",
    "javascript:S4084": "Accessibility",
    "javascript:S5254": "Accessibility",
    "javascript:S6819": "Accessibility",
    "javascript:S6825": "Accessibility",
    "javascript:S6827": "Accessibility",
    "javascript:S6842": "Accessibility",
    "javascript:S6844": "Accessibility",
    "javascript:S6848": "Accessibility",
    "javascript:S6853": "Accessibility",
    # TypeScript accessibility
    "typescript:S1077": "Accessibility",
    "typescript:S1082": "Accessibility",
    "typescript:S1090": "Accessibility",
    "typescript:S4084": "Accessibility",
    "typescript:S5254": "Accessibility",
    "typescript:S5256": "Accessibility",
    "typescript:S6807": "Accessibility",
    "typescript:S6811": "Accessibility",
    "typescript:S6819": "Accessibility",
    "typescript:S6821": "Accessibility",
    "typescript:S6822": "Accessibility",
    "typescript:S6825": "Accessibility",
    "typescript:S6827": "Accessibility",
    "typescript:S6841": "Accessibility",
    "typescript:S6842": "Accessibility",
    "typescript:S6843": "Accessibility",
    "typescript:S6844": "Accessibility",
    "typescript:S6845": "Accessibility",
    "typescript:S6847": "Accessibility",
    "typescript:S6848": "Accessibility",
    "typescript:S6850": "Accessibility",
    "typescript:S6851": "Accessibility",
    "typescript:S6852": "Accessibility",
    "typescript:S6853": "Accessibility",
    # =========================================================================
    # 3. LOGIC ERRORS - Actual bugs in code logic
    # Hypothesis: Core AI competency test - should decrease if AI helps
    # Expected: ↓ decrease if AI effective
    # =========================================================================
    # Sorting without compare function (S2871)
    "javascript:S2871": "Logic Error",
    "typescript:S2871": "Logic Error",
    # Self-assignment / identical expressions (S1656, S1764)
    "go:S1764": "Logic Error",
    "java:S1656": "Logic Error",
    "javascript:S1656": "Logic Error",
    "javascript:S1764": "Logic Error",
    "php:S1656": "Logic Error",
    "python:S1656": "Logic Error",
    "python:S1764": "Logic Error",
    "typescript:S1656": "Logic Error",
    "typescript:S1764": "Logic Error",
    # Comparison issues
    "javascript:S3403": "Logic Error",
    "python:S3403": "Logic Error",
    "java:S4973": "Logic Error",
    "python:S1244": "Logic Error",
    "python:S5795": "Logic Error",
    "python:S5796": "Logic Error",
    # Null/undefined issues (S2259)
    "java:S2259": "Logic Error",
    "javascript:S2259": "Logic Error",
    "javascript:S6523": "Logic Error",
    "typescript:S6523": "Logic Error",
    # Constant conditions (S2589, S6638)
    "java:S2589": "Logic Error",
    "javascript:S2589": "Logic Error",
    "typescript:S2589": "Logic Error",
    "javascript:S6638": "Logic Error",
    "typescript:S6638": "Logic Error",
    "php:S5797": "Logic Error",
    "python:S5797": "Logic Error",
    # Identical branches (S1871, S3923)
    "go:S1871": "Logic Error",
    "java:S1871": "Logic Error",
    "javascript:S1871": "Logic Error",
    "kotlin:S1871": "Logic Error",
    "php:S1871": "Logic Error",
    "python:S1871": "Logic Error",
    "typescript:S1871": "Logic Error",
    "go:S3923": "Logic Error",
    "java:S3923": "Logic Error",
    "javascript:S3923": "Logic Error",
    "python:S3923": "Logic Error",
    "typescript:S3923": "Logic Error",
    # Duplicate conditions (S1862)
    "go:S1862": "Logic Error",
    "javascript:S1862": "Logic Error",
    "python:S1862": "Logic Error",
    "typescript:S1862": "Logic Error",
    # Statement indentation issues (S2681)
    "java:S2681": "Logic Error",
    "javascript:S2681": "Logic Error",
    "typescript:S2681": "Logic Error",
    # Unreachable/dead code (S1763)
    "go:S1763": "Logic Error",
    "ipython:S1763": "Logic Error",
    "java:S1763": "Logic Error",
    "javascript:S1763": "Logic Error",
    "php:S1763": "Logic Error",
    "python:S1763": "Logic Error",
    "typescript:S1763": "Logic Error",
    # Loop issues (S1751)
    "java:S1751": "Logic Error",
    "javascript:S1751": "Logic Error",
    "python:S1751": "Logic Error",
    "typescript:S1751": "Logic Error",
    "javascript:S2189": "Logic Error",
    # Return value not used (S2201)
    "java:S2201": "Logic Error",
    "javascript:S2201": "Logic Error",
    "python:S2201": "Logic Error",
    "typescript:S2201": "Logic Error",
    "java:S899": "Logic Error",
    "kotlin:S899": "Logic Error",
    # Promise/async errors
    "javascript:S6671": "Logic Error",
    "typescript:S6671": "Logic Error",
    "javascript:S4822": "Logic Error",
    "typescript:S4822": "Logic Error",
    "javascript:S6544": "Logic Error",
    "typescript:S6544": "Logic Error",
    # Function output not used (S3699)
    "java:S3699": "Logic Error",
    "javascript:S3699": "Logic Error",
    "php:S3699": "Logic Error",
    "python:S3699": "Logic Error",
    "typescript:S3699": "Logic Error",
    # Type errors
    "java:S2153": "Logic Error",
    "java:S2159": "Logic Error",
    "python:S2159": "Logic Error",
    # Operator errors
    "java:S2178": "Logic Error",
    "java:S2184": "Logic Error",
    # =========================================================================
    # 4. CODE COMPLEXITY - Structural/maintainability issues
    # Hypothesis: AI iterative edits may increase complexity
    # Expected: ↑ increase from iterative AI editing
    # =========================================================================
    # Cognitive complexity (S3776)
    "go:S3776": "Code Complexity",
    "ipython:S3776": "Code Complexity",
    "java:S3776": "Code Complexity",
    "javascript:S3776": "Code Complexity",
    "kotlin:S3776": "Code Complexity",
    "php:S3776": "Code Complexity",
    "python:S3776": "Code Complexity",
    "ruby:S3776": "Code Complexity",
    "typescript:S3776": "Code Complexity",
    # Deep function nesting (S2004)
    "javascript:S2004": "Code Complexity",
    "typescript:S2004": "Code Complexity",
    # Nested ternary (S3358)
    "ipython:S3358": "Code Complexity",
    "java:S3358": "Code Complexity",
    "javascript:S3358": "Code Complexity",
    "php:S3358": "Code Complexity",
    "python:S3358": "Code Complexity",
    "typescript:S3358": "Code Complexity",
    # Too many parameters (S107)
    "go:S107": "Code Complexity",
    "java:S107": "Code Complexity",
    "javascript:S107": "Code Complexity",
    "kotlin:S107": "Code Complexity",
    "php:S107": "Code Complexity",
    "python:S107": "Code Complexity",
    "ruby:S107": "Code Complexity",
    "typescript:S107": "Code Complexity",
    # Too many switch cases (S1479)
    "go:S1479": "Code Complexity",
    "javascript:S1479": "Code Complexity",
    "typescript:S1479": "Code Complexity",
    # Function/class too long
    "php:S138": "Code Complexity",
    "php:S1142": "Code Complexity",
    "php:S1448": "Code Complexity",
    # Duplicate functions (S4144)
    "go:S4144": "Code Complexity",
    "java:S4144": "Code Complexity",
    "javascript:S4144": "Code Complexity",
    "php:S4144": "Code Complexity",
    "python:S4144": "Code Complexity",
    "ruby:S4144": "Code Complexity",
    "typescript:S4144": "Code Complexity",
    # String literal duplication (S1192)
    "azureresourcemanager:S1192": "Code Complexity",
    "go:S1192": "Code Complexity",
    "ipython:S1192": "Code Complexity",
    "java:S1192": "Code Complexity",
    "kotlin:S1192": "Code Complexity",
    "php:S1192": "Code Complexity",
    "python:S1192": "Code Complexity",
    "ruby:S1192": "Code Complexity",
    # =========================================================================
    # 5. REACT PATTERNS - React/frontend framework issues
    # Hypothesis: AI reproduces common anti-patterns from training data
    # =========================================================================
    # Array index in keys (S6479)
    "javascript:S6479": "React Patterns",
    "typescript:S6479": "React Patterns",
    # Component naming (S6770)
    "javascript:S6770": "React Patterns",
    "typescript:S6770": "React Patterns",
    # Missing key prop (S6477)
    "javascript:S6477": "React Patterns",
    "typescript:S6477": "React Patterns",
    # Hook violations (S6440, S6443)
    "javascript:S6440": "React Patterns",
    "typescript:S6440": "React Patterns",
    "javascript:S6443": "React Patterns",
    "typescript:S6443": "React Patterns",
    # State mutations (S6746, S6756)
    "javascript:S6746": "React Patterns",
    "javascript:S6756": "React Patterns",
    "typescript:S6756": "React Patterns",
    # Component definition in render (S6478)
    "javascript:S6478": "React Patterns",
    "typescript:S6478": "React Patterns",
    # Context provider issues (S6481)
    "javascript:S6481": "React Patterns",
    "typescript:S6481": "React Patterns",
    # PropTypes issues (S6767, S6774, S6775)
    "javascript:S6767": "React Patterns",
    "typescript:S6767": "React Patterns",
    "javascript:S6774": "React Patterns",
    "javascript:S6775": "React Patterns",
    "typescript:S6775": "React Patterns",
    # Deprecated React APIs (S6788, S6791, S6957)
    "javascript:S6788": "React Patterns",
    "javascript:S6791": "React Patterns",
    "typescript:S6791": "React Patterns",
    "typescript:S6957": "React Patterns",
    # JSX issues (S6747, S6748, S6749, S6438, S6439)
    "javascript:S6747": "React Patterns",
    "typescript:S6747": "React Patterns",
    "javascript:S6748": "React Patterns",
    "typescript:S6748": "React Patterns",
    "javascript:S6749": "React Patterns",
    "typescript:S6749": "React Patterns",
    "typescript:S6438": "React Patterns",
    "typescript:S6439": "React Patterns",
    # useState destructuring (S6754)
    "javascript:S6754": "React Patterns",
    "typescript:S6754": "React Patterns",
    # Generated keys (S6486)
    "typescript:S6486": "React Patterns",
    # Class component issues (S6441, S6757)
    "javascript:S6441": "React Patterns",
    "typescript:S6441": "React Patterns",
    "javascript:S6757": "React Patterns",
    "typescript:S6757": "React Patterns",
    # =========================================================================
    # 6. TYPE SAFETY - Type system issues (primarily TypeScript)
    # =========================================================================
    # Unnecessary type assertions (S4325)
    "typescript:S4325": "Type Safety",
    # Props readonly (S6759)
    "typescript:S6759": "Type Safety",
    # Generic issues
    "java:S1452": "Type Safety",
    "java:S2326": "Type Safety",
    "java:S3740": "Type Safety",
    "typescript:S6569": "Type Safety",
    "typescript:S6571": "Type Safety",
    # Type alias issues (S4323, S6564, S6565)
    "typescript:S4323": "Type Safety",
    "typescript:S6564": "Type Safety",
    "typescript:S6565": "Type Safety",
    # Enum issues
    "typescript:S6550": "Type Safety",
    "typescript:S6572": "Type Safety",
    "typescript:S6578": "Type Safety",
    "typescript:S6583": "Type Safety",
    # Union/intersection type issues
    "typescript:S4335": "Type Safety",
    "typescript:S4621": "Type Safety",
    "typescript:S4623": "Type Safety",
    "typescript:S4782": "Type Safety",
    # =========================================================================
    # 7. API USAGE - Deprecated/incorrect API usage
    # Hypothesis: AI training data contains outdated patterns
    # Expected: ↑ increase (stale training data)
    # =========================================================================
    "java:S1133": "API Usage",
    "java:S1191": "API Usage",
    "java:S1874": "API Usage",
    "javascript:S1874": "API Usage",
    "kotlin:S1133": "API Usage",
    "kotlin:S1874": "API Usage",
    "kubernetes:S1874": "API Usage",
    "php:S1874": "API Usage",
    "typescript:S1874": "API Usage",
    "javascript:S6653": "API Usage",
    "typescript:S6653": "API Usage",
    "javascript:S6654": "API Usage",
    "typescript:S6654": "API Usage",
    "Web:S1827": "API Usage",
    "Web:UnsupportedTagsInHtml5Check": "API Usage",
    # =========================================================================
    # 8. SECURITY - Vulnerabilities and security issues
    # Hypothesis: AI may reproduce insecure patterns from training data
    # =========================================================================
    "docker:S6437": "Security",
    "java:S2115": "Security",
    "javascript:S2819": "Security",
    "javascript:S4426": "Security",
    "javascript:S4830": "Security",
    "javascript:S5542": "Security",
    "kubernetes:S6864": "Security",
    "kubernetes:S6865": "Security",
    "kubernetes:S6867": "Security",
    "kubernetes:S6870": "Security",
    "python:S2053": "Security",
    "python:S2755": "Security",
    "python:S4830": "Security",
    "python:S5445": "Security",
    "python:S5527": "Security",
    "python:S5659": "Security",
    "python:S6779": "Security",
    "secrets:S6334": "Security",
    "secrets:S6335": "Security",
    "secrets:S6687": "Security",
    "secrets:S6693": "Security",
    "secrets:S6697": "Security",
    "secrets:S6698": "Security",
    "secrets:S6703": "Security",
    "secrets:S6706": "Security",
    "secrets:S6739": "Security",
    "terraform:S4423": "Security",
    "terraform:S6321": "Security",
    "typescript:S2598": "Security",
    "typescript:S2819": "Security",
    "typescript:S5542": "Security",
    # =========================================================================
    # 9. NAMING CONVENTIONS - Style/naming issues
    # Hypothesis: AI may not follow project-specific conventions
    # =========================================================================
    "go:S100": "Naming Conventions",
    "go:S117": "Naming Conventions",
    "ipython:S117": "Naming Conventions",
    "ipython:S1542": "Naming Conventions",
    "ipython:S1700": "Naming Conventions",
    "java:S100": "Naming Conventions",
    "java:S101": "Naming Conventions",
    "java:S115": "Naming Conventions",
    "java:S116": "Naming Conventions",
    "java:S117": "Naming Conventions",
    "java:S119": "Naming Conventions",
    "java:S120": "Naming Conventions",
    "java:S1700": "Naming Conventions",
    "java:S1845": "Naming Conventions",
    "java:S3008": "Naming Conventions",
    "javascript:S101": "Naming Conventions",
    "javascript:S2137": "Naming Conventions",
    "javascript:S2430": "Naming Conventions",
    "kotlin:S100": "Naming Conventions",
    "php:S100": "Naming Conventions",
    "php:S101": "Naming Conventions",
    "php:S114": "Naming Conventions",
    "php:S115": "Naming Conventions",
    "php:S116": "Naming Conventions",
    "php:S117": "Naming Conventions",
    "python:S100": "Naming Conventions",
    "python:S101": "Naming Conventions",
    "python:S116": "Naming Conventions",
    "python:S117": "Naming Conventions",
    "python:S1542": "Naming Conventions",
    "python:S1700": "Naming Conventions",
    "python:S1845": "Naming Conventions",
    "ruby:S100": "Naming Conventions",
    "ruby:S101": "Naming Conventions",
    "ruby:S117": "Naming Conventions",
    "terraform:S6273": "Naming Conventions",
    "typescript:S101": "Naming Conventions",
    "typescript:S2137": "Naming Conventions",
    "typescript:S2430": "Naming Conventions",
    # =========================================================================
    # 10. ERROR HANDLING - Exception/error handling issues
    # Hypothesis: AI may generate incomplete error handling
    # =========================================================================
    # Empty blocks (S108)
    "go:S108": "Error Handling",
    "ipython:S108": "Error Handling",
    "java:S108": "Error Handling",
    "javascript:S108": "Error Handling",
    "kotlin:S108": "Error Handling",
    "php:S108": "Error Handling",
    "python:S108": "Error Handling",
    "ruby:S108": "Error Handling",
    "typescript:S108": "Error Handling",
    # Generic exceptions (S112)
    "java:S112": "Error Handling",
    "php:S112": "Error Handling",
    "python:S112": "Error Handling",
    # Exception handling issues
    "java:S1130": "Error Handling",
    "java:S1141": "Error Handling",
    "java:S2142": "Error Handling",
    "java:S2147": "Error Handling",
    "javascript:S1143": "Error Handling",
    "python:S1143": "Error Handling",
    "typescript:S1143": "Error Handling",
    "javascript:S2737": "Error Handling",
    "python:S2737": "Error Handling",
    "typescript:S2737": "Error Handling",
    "typescript:S2486": "Error Handling",
    "javascript:S3696": "Error Handling",
    "typescript:S3696": "Error Handling",
    "php:S5713": "Error Handling",
    "python:S5709": "Error Handling",
    "python:S5713": "Error Handling",
    "python:S5747": "Error Handling",
    "python:S5754": "Error Handling",
    "python:S3984": "Error Handling",
    "python:S5632": "Error Handling",
    # =========================================================================
    # 11. EMPTY/INCOMPLETE CODE - Missing implementations
    # Hypothesis: AI may generate stubs without implementation
    # =========================================================================
    # Empty methods/functions (S1186)
    "go:S1186": "Empty/Incomplete Code",
    "ipython:S1186": "Empty/Incomplete Code",
    "java:S1186": "Empty/Incomplete Code",
    "javascript:S1186": "Empty/Incomplete Code",
    "kotlin:S1186": "Empty/Incomplete Code",
    "php:S1186": "Empty/Incomplete Code",
    "python:S1186": "Empty/Incomplete Code",
    "ruby:S1186": "Empty/Incomplete Code",
    "typescript:S1186": "Empty/Incomplete Code",
    # Empty classes (S2094)
    "java:S2094": "Empty/Incomplete Code",
    "javascript:S2094": "Empty/Incomplete Code",
    "typescript:S2094": "Empty/Incomplete Code",
    # Empty CSS
    "css:S4658": "Empty/Incomplete Code",
    "css:S4667": "Empty/Incomplete Code",
    # =========================================================================
    # 12. REGEX ISSUES - Regular expression problems
    # Hypothesis: AI-generated regex may be overly complex or incorrect
    # =========================================================================
    # Regex complexity (S5843)
    "java:S5843": "Regex Issues",
    "javascript:S5843": "Regex Issues",
    "php:S5843": "Regex Issues",
    "python:S5843": "Regex Issues",
    "typescript:S5843": "Regex Issues",
    # Duplicate character class (S5869)
    "ipython:S5869": "Regex Issues",
    "java:S5869": "Regex Issues",
    "javascript:S5869": "Regex Issues",
    "php:S5869": "Regex Issues",
    "python:S5869": "Regex Issues",
    "typescript:S5869": "Regex Issues",
    # Empty match (S5842)
    "javascript:S5842": "Regex Issues",
    "php:S5842": "Regex Issues",
    "python:S5842": "Regex Issues",
    "typescript:S5842": "Regex Issues",
    # Operator precedence (S5850)
    "javascript:S5850": "Regex Issues",
    "php:S5850": "Regex Issues",
    "python:S5850": "Regex Issues",
    "typescript:S5850": "Regex Issues",
    # Reluctant quantifiers (S6019)
    "javascript:S6019": "Regex Issues",
    "php:S6019": "Regex Issues",
    "python:S6019": "Regex Issues",
    "typescript:S6019": "Regex Issues",
    # Alternation vs character class (S6035)
    "javascript:S6035": "Regex Issues",
    "php:S6035": "Regex Issues",
    "python:S6035": "Regex Issues",
    "typescript:S6035": "Regex Issues",
    # Empty alternative (S6323)
    "javascript:S6323": "Regex Issues",
    "python:S6323": "Regex Issues",
    "typescript:S6323": "Regex Issues",
    # Control characters (S6324)
    "javascript:S6324": "Regex Issues",
    "typescript:S6324": "Regex Issues",
    # RegExp constructor (S6325)
    "javascript:S6325": "Regex Issues",
    "typescript:S6325": "Regex Issues",
    # Multiple spaces (S6326)
    "javascript:S6326": "Regex Issues",
    "python:S6326": "Regex Issues",
    # Concise character class (S6353)
    "ipython:S6353": "Regex Issues",
    "java:S6353": "Regex Issues",
    "javascript:S6353": "Regex Issues",
    "php:S6353": "Regex Issues",
    "python:S6353": "Regex Issues",
    "typescript:S6353": "Regex Issues",
    # Single char class (S6397)
    "javascript:S6397": "Regex Issues",
    "python:S6397": "Regex Issues",
    "typescript:S6397": "Regex Issues",
    # Grouped subpattern (S6395)
    "php:S6395": "Regex Issues",
    "python:S6395": "Regex Issues",
    # Unnecessary quantifier (S6396)
    "php:S6396": "Regex Issues",
    "python:S6396": "Regex Issues",
    # Reluctant quantifier replacement (S5857)
    "php:S5857": "Regex Issues",
    "python:S5857": "Regex Issues",
    # Other regex issues
    "javascript:S5868": "Regex Issues",
    "python:S5855": "Regex Issues",
    "python:S5996": "Regex Issues",
    "typescript:S5860": "Regex Issues",
    "typescript:S6331": "Regex Issues",
    "typescript:S6351": "Regex Issues",
    # =========================================================================
    # 13. CONCURRENCY - Threading and async issues
    # Hypothesis: AI may not handle async patterns correctly
    # =========================================================================
    "java:S1149": "Concurrency",
    "java:S2119": "Concurrency",
    "java:S2168": "Concurrency",
    "java:S2696": "Concurrency",
    "java:S2885": "Concurrency",
    "java:S2886": "Concurrency",
    "java:S3014": "Concurrency",
    "java:S3064": "Concurrency",
    "java:S3077": "Concurrency",
    "java:S3078": "Concurrency",
    "java:S5164": "Concurrency",
    "javascript:S4123": "Concurrency",
    "typescript:S4123": "Concurrency",
    "javascript:S4634": "Concurrency",
    "typescript:S4634": "Concurrency",
    "javascript:S7059": "Concurrency",
    "typescript:S7059": "Concurrency",
    # =========================================================================
    # 14. RESOURCE MANAGEMENT - Memory/resource leaks
    # =========================================================================
    "java:S2093": "Resource Management",
    "java:S2095": "Resource Management",
    "java:S4042": "Resource Management",
    "java:S4087": "Resource Management",
    # =========================================================================
    # 15. CODE STYLE - Formatting and style preferences
    # =========================================================================
    # Boolean literals (S1125)
    "go:S1125": "Code Style",
    "java:S1125": "Code Style",
    "javascript:S1125": "Code Style",
    "kotlin:S1125": "Code Style",
    "php:S1125": "Code Style",
    "typescript:S1125": "Code Style",
    # Negation operators (S1940)
    "go:S1940": "Code Style",
    "javascript:S1940": "Code Style",
    "python:S1940": "Code Style",
    "typescript:S1940": "Code Style",
    # Loop style (S1264)
    "java:S1264": "Code Style",
    "javascript:S1264": "Code Style",
    "typescript:S1264": "Code Style",
    # Switch vs if (S1301)
    "java:S1301": "Code Style",
    "javascript:S1301": "Code Style",
    "php:S1301": "Code Style",
    "typescript:S1301": "Code Style",
    # Formatting
    "css:S1116": "Code Style",
    "java:S1116": "Code Style",
    "php:S1116": "Code Style",
    "php:S105": "Code Style",
    "php:S1109": "Code Style",
    "php:S113": "Code Style",
    "php:S1131": "Code Style",
    # Return style (S1126, S1488)
    "java:S1126": "Code Style",
    "javascript:S1126": "Code Style",
    "java:S1488": "Code Style",
    "php:S1488": "Code Style",
    # Modern syntax preferences
    "javascript:S6661": "Code Style",
    "typescript:S6661": "Code Style",
    "javascript:S6666": "Code Style",
    "typescript:S6666": "Code Style",
    "javascript:S6582": "Code Style",
    "typescript:S6582": "Code Style",
    "typescript:S6606": "Code Style",
    # =========================================================================
    # 16. INFRASTRUCTURE - Docker/Kubernetes/IaC issues
    # =========================================================================
    "docker:S6476": "Infrastructure",
    "docker:S6570": "Infrastructure",
    "docker:S6573": "Infrastructure",
    "docker:S6579": "Infrastructure",
    "docker:S6584": "Infrastructure",
    "docker:S6587": "Infrastructure",
    "docker:S6589": "Infrastructure",
    "docker:S6595": "Infrastructure",
    "docker:S6596": "Infrastructure",
    "docker:S6597": "Infrastructure",
    "docker:S7018": "Infrastructure",
    "docker:S7019": "Infrastructure",
    "docker:S7020": "Infrastructure",
    "docker:S7026": "Infrastructure",
    "docker:S7029": "Infrastructure",
    "docker:S7031": "Infrastructure",
    "kubernetes:S6596": "Infrastructure",
    "kubernetes:S6873": "Infrastructure",
    "kubernetes:S6892": "Infrastructure",
    "kubernetes:S6893": "Infrastructure",
    "kubernetes:S6897": "Infrastructure",
    "kubernetes:S6907": "Infrastructure",
    "azureresourcemanager:S6874": "Infrastructure",
    "azureresourcemanager:S6975": "Infrastructure",
    # =========================================================================
    # 17. CSS ISSUES - Stylesheet-specific problems
    # =========================================================================
    "css:S4648": "CSS Issues",
    "css:S4649": "CSS Issues",
    "css:S4650": "CSS Issues",
    "css:S4651": "CSS Issues",
    "css:S4653": "CSS Issues",
    "css:S4654": "CSS Issues",
    "css:S4656": "CSS Issues",
    "css:S4657": "CSS Issues",
    "css:S4659": "CSS Issues",
    "css:S4660": "CSS Issues",
    "css:S4662": "CSS Issues",
    "css:S4666": "CSS Issues",
    "css:S4670": "CSS Issues",
    # =========================================================================
    # 18. DATA SCIENCE - Python ML/data science specific
    # =========================================================================
    "ipython:S6709": "Data Science",
    "ipython:S6734": "Data Science",
    "ipython:S6969": "Data Science",
    "python:S6709": "Data Science",
    "python:S6711": "Data Science",
    "python:S6729": "Data Science",
    "python:S6730": "Data Science",
    "python:S6734": "Data Science",
    "python:S6735": "Data Science",
    "python:S6929": "Data Science",
    "python:S6973": "Data Science",
    "python:S6984": "Data Science",
    # =========================================================================
    # 19. HTML STRUCTURE - HTML document structure issues
    # =========================================================================
    "Web:DoctypePresenceCheck": "HTML Structure",
    "Web:ItemTagNotWithinContainerTagCheck": "HTML Structure",
    "Web:MetaRefreshCheck": "HTML Structure",
    "Web:S4645": "HTML Structure",
}


# ============================================================================
# CATEGORY METADATA
# ============================================================================

CATEGORY_METADATA = {
    "Code Hygiene": {
        "hypothesis": "AI scaffolding leaves artifacts (TODOs, commented code)",
        "expected_direction": "increase",
        "ai_relevance": "high",
    },
    "Accessibility": {
        "hypothesis": "AI training data underrepresents a11y patterns",
        "expected_direction": "increase",
        "ai_relevance": "medium",
    },
    "Logic Error": {
        "hypothesis": "Core AI competency - should reduce bugs",
        "expected_direction": "decrease",
        "ai_relevance": "high",
    },
    "Code Complexity": {
        "hypothesis": "Iterative AI edits may increase nesting/complexity",
        "expected_direction": "increase",
        "ai_relevance": "high",
    },
    "React Patterns": {
        "hypothesis": "AI reproduces anti-patterns from training data",
        "expected_direction": "mixed",
        "ai_relevance": "high",
    },
    "Type Safety": {
        "hypothesis": "AI may over/under-specify types",
        "expected_direction": "mixed",
        "ai_relevance": "medium",
    },
    "API Usage": {
        "hypothesis": "AI training data contains outdated patterns",
        "expected_direction": "increase",
        "ai_relevance": "medium",
    },
    "Security": {
        "hypothesis": "AI may reproduce insecure patterns",
        "expected_direction": "mixed",
        "ai_relevance": "medium",
    },
    "Naming Conventions": {
        "hypothesis": "AI may not follow project conventions",
        "expected_direction": "mixed",
        "ai_relevance": "low",
    },
    "Error Handling": {
        "hypothesis": "AI may generate incomplete error handling",
        "expected_direction": "increase",
        "ai_relevance": "medium",
    },
    "Empty/Incomplete Code": {
        "hypothesis": "AI may generate stubs without implementation",
        "expected_direction": "increase",
        "ai_relevance": "high",
    },
    "Regex Issues": {
        "hypothesis": "AI-generated regex may be complex or incorrect",
        "expected_direction": "increase",
        "ai_relevance": "high",
    },
    "Concurrency": {
        "hypothesis": "AI may not handle async correctly",
        "expected_direction": "mixed",
        "ai_relevance": "medium",
    },
    "Resource Management": {
        "hypothesis": "AI may not properly manage resources",
        "expected_direction": "mixed",
        "ai_relevance": "low",
    },
    "Code Style": {
        "hypothesis": "AI may not follow consistent style",
        "expected_direction": "mixed",
        "ai_relevance": "low",
    },
    "Infrastructure": {
        "hypothesis": "AI may generate suboptimal container configs",
        "expected_direction": "mixed",
        "ai_relevance": "medium",
    },
    "CSS Issues": {
        "hypothesis": "AI may generate invalid CSS",
        "expected_direction": "mixed",
        "ai_relevance": "medium",
    },
    "Data Science": {
        "hypothesis": "AI may miss ML best practices",
        "expected_direction": "mixed",
        "ai_relevance": "medium",
    },
    "HTML Structure": {
        "hypothesis": "AI may generate invalid HTML structure",
        "expected_direction": "mixed",
        "ai_relevance": "low",
    },
}


def get_category(rule: str) -> str:
    """Get category for a rule, returns 'Other' if not mapped."""
    return RULE_TO_CATEGORY.get(rule, "Other")


def categorize_dataframe(df, rule_column="rule"):
    """Add category column to a dataframe."""
    df = df.copy()
    df["category"] = df[rule_column].map(get_category)
    return df


if __name__ == "__main__":
    from collections import Counter
    from pathlib import Path

    import pandas as pd

    # Get paths
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent
    input_file = project_dir / "data" / "sonarqube_warning_definitions.csv"
    output_file = project_dir / "data" / "sonarqube_warning_definitions.csv"

    # Read the CSV file
    print(f"Reading from: {input_file}")
    df = pd.read_csv(input_file)
    print(f"Loaded {len(df)} rules")

    # Add category column
    df["category"] = df["rule"].map(get_category)

    # Save to new file
    df.to_csv(output_file, index=False)
    print(f"\nSaved categorized data to: {output_file}")

    # Print summary statistics
    print("\n" + "=" * 70)
    print("CATEGORY SUMMARY")
    print("=" * 70)

    category_counts = df["category"].value_counts()
    for cat, count in category_counts.items():
        meta = CATEGORY_METADATA.get(cat, {})
        direction = meta.get("expected_direction", "unknown")
        hypothesis = meta.get("hypothesis", "N/A")
        print(f"\n{cat}: {count} rules (expected: {direction})")
        print(f"  Hypothesis: {hypothesis}")

    print("\n" + "=" * 70)
    print(f"Total rules in CSV: {len(df)}")
    print(f"Total rules mapped: {len(RULE_TO_CATEGORY)}")
    print(f"Rules categorized as 'Other': {(df['category'] == 'Other').sum()}")
    print("=" * 70)
