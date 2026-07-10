#!/usr/bin/env bash
set -euo pipefail

echo '=== zauberzeug/nicegui 2025-04 ncloc ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 2b8b1a696992e64578f2e4c5fc285e90b60b87a6 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 2b8b1a696992e64578f2e4c5fc285e90b60b87a6 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 2b8b1a696992e64578f2e4c5fc285e90b60b87a6:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 2b8b1a696992e64578f2e4c5fc285e90b60b87a6:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-04 ncloc ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 08f147eb9879e899fb7939f4b9413c86164ba7f9 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 08f147eb9879e899fb7939f4b9413c86164ba7f9 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 08f147eb9879e899fb7939f4b9413c86164ba7f9:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 08f147eb9879e899fb7939f4b9413c86164ba7f9:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-08 ncloc ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 79cf381322842888a721905c09490e85f98a5a2a | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 79cf381322842888a721905c09490e85f98a5a2a | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 79cf381322842888a721905c09490e85f98a5a2a:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 79cf381322842888a721905c09490e85f98a5a2a:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-07 ncloc ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-06 ncloc ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only bf87ddcb0e02027bb8c1e7a1aa2e03f0c4312e90 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only bf87ddcb0e02027bb8c1e7a1aa2e03f0c4312e90 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show bf87ddcb0e02027bb8c1e7a1aa2e03f0c4312e90:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show bf87ddcb0e02027bb8c1e7a1aa2e03f0c4312e90:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-04 technical_debt ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 2b8b1a696992e64578f2e4c5fc285e90b60b87a6 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 2b8b1a696992e64578f2e4c5fc285e90b60b87a6 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 2b8b1a696992e64578f2e4c5fc285e90b60b87a6:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 2b8b1a696992e64578f2e4c5fc285e90b60b87a6:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-05 ncloc ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only fa2cab6b204f2efeabb5c5bbc1d35ff23c91ec8b | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only fa2cab6b204f2efeabb5c5bbc1d35ff23c91ec8b | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show fa2cab6b204f2efeabb5c5bbc1d35ff23c91ec8b:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show fa2cab6b204f2efeabb5c5bbc1d35ff23c91ec8b:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-03 ncloc ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only ecdaddcfaf15967165806e2cd4f9bc0cfb40f0e1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only ecdaddcfaf15967165806e2cd4f9bc0cfb40f0e1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show ecdaddcfaf15967165806e2cd4f9bc0cfb40f0e1:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show ecdaddcfaf15967165806e2cd4f9bc0cfb40f0e1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-02 ncloc ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only e6cdfed56138f74a1e8bcac05f60036d96ab9a6a | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only e6cdfed56138f74a1e8bcac05f60036d96ab9a6a | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show e6cdfed56138f74a1e8bcac05f60036d96ab9a6a:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show e6cdfed56138f74a1e8bcac05f60036d96ab9a6a:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-02 technical_debt ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b71074ef73498f532234a837ea04a08ffbf4e804 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b71074ef73498f532234a837ea04a08ffbf4e804 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show b71074ef73498f532234a837ea04a08ffbf4e804:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show b71074ef73498f532234a837ea04a08ffbf4e804:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-01 technical_debt ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 7a540bf3dded6f1e58d32bf21a97d9a5c013afc1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 7a540bf3dded6f1e58d32bf21a97d9a5c013afc1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 7a540bf3dded6f1e58d32bf21a97d9a5c013afc1:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 7a540bf3dded6f1e58d32bf21a97d9a5c013afc1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-03 technical_debt ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 745167c81c219beda5ebaf850dfb7a3e772f96ac | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 745167c81c219beda5ebaf850dfb7a3e772f96ac | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 745167c81c219beda5ebaf850dfb7a3e772f96ac:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 745167c81c219beda5ebaf850dfb7a3e772f96ac:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-12 technical_debt ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 343dc0da8de0cf2f645cf8b5d76f5b439cb817f3 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 343dc0da8de0cf2f645cf8b5d76f5b439cb817f3 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 343dc0da8de0cf2f645cf8b5d76f5b439cb817f3:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 343dc0da8de0cf2f645cf8b5d76f5b439cb817f3:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-11 technical_debt ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 25a633450d1223dcc8f1ad59d260d2e844b5519d | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 25a633450d1223dcc8f1ad59d260d2e844b5519d | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 25a633450d1223dcc8f1ad59d260d2e844b5519d:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 25a633450d1223dcc8f1ad59d260d2e844b5519d:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-01 ncloc ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 1253d960c415d65583dac034353702ad74016da1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 1253d960c415d65583dac034353702ad74016da1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 1253d960c415d65583dac034353702ad74016da1:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 1253d960c415d65583dac034353702ad74016da1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2024-12 ncloc ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 3aa25f3257f981db0b7e8b5411dc209b66c6f4c2 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 3aa25f3257f981db0b7e8b5411dc209b66c6f4c2 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 3aa25f3257f981db0b7e8b5411dc209b66c6f4c2:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 3aa25f3257f981db0b7e8b5411dc209b66c6f4c2:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2024-11 ncloc ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only b4d51e3b746e6174a7d60c525ea22387f00dcafe | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only b4d51e3b746e6174a7d60c525ea22387f00dcafe | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show b4d51e3b746e6174a7d60c525ea22387f00dcafe:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show b4d51e3b746e6174a7d60c525ea22387f00dcafe:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-04 cognitive_complexity ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 2b8b1a696992e64578f2e4c5fc285e90b60b87a6 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 2b8b1a696992e64578f2e4c5fc285e90b60b87a6 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 2b8b1a696992e64578f2e4c5fc285e90b60b87a6:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 2b8b1a696992e64578f2e4c5fc285e90b60b87a6:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2024-10 ncloc ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 12ff477551dfc5a197aca3006e14e4193183dbd8 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 12ff477551dfc5a197aca3006e14e4193183dbd8 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 12ff477551dfc5a197aca3006e14e4193183dbd8:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 12ff477551dfc5a197aca3006e14e4193183dbd8:pyproject.toml 2>/dev/null | head -120 || true


echo '=== wdm0006/elote 2025-02 cognitive_complexity ==='
git -C '../treatment-repos/wdm0006_elote' rev-parse --is-inside-work-tree
git -C '../treatment-repos/wdm0006_elote' ls-tree -r --name-only 6371b529b88402434e8cafaaf0ed137b412bfd6b | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/wdm0006_elote' ls-tree -r --name-only 6371b529b88402434e8cafaaf0ed137b412bfd6b | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/wdm0006_elote' show 6371b529b88402434e8cafaaf0ed137b412bfd6b:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/wdm0006_elote' show 6371b529b88402434e8cafaaf0ed137b412bfd6b:pyproject.toml 2>/dev/null | head -120 || true


echo '=== wdm0006/elote 2024-07 cognitive_complexity ==='
git -C '../treatment-repos/wdm0006_elote' rev-parse --is-inside-work-tree
git -C '../treatment-repos/wdm0006_elote' ls-tree -r --name-only 75739e6ad51f3d50fdd047a0136f56b6274ad080 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/wdm0006_elote' ls-tree -r --name-only 75739e6ad51f3d50fdd047a0136f56b6274ad080 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/wdm0006_elote' show 75739e6ad51f3d50fdd047a0136f56b6274ad080:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/wdm0006_elote' show 75739e6ad51f3d50fdd047a0136f56b6274ad080:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2024-09 ncloc ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 761c6ce0ab4db14ddede62cb61b6d6854dff7ea7 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 761c6ce0ab4db14ddede62cb61b6d6854dff7ea7 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 761c6ce0ab4db14ddede62cb61b6d6854dff7ea7:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 761c6ce0ab4db14ddede62cb61b6d6854dff7ea7:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2025-08 ncloc ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 47747287b616d4a2f1dd14f811f218e3caee7f8d | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 47747287b616d4a2f1dd14f811f218e3caee7f8d | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show 47747287b616d4a2f1dd14f811f218e3caee7f8d:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show 47747287b616d4a2f1dd14f811f218e3caee7f8d:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2025-07 ncloc ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only c7afa724ddf1a3a5ff0633edc75c93570b9a5689 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only c7afa724ddf1a3a5ff0633edc75c93570b9a5689 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show c7afa724ddf1a3a5ff0633edc75c93570b9a5689:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show c7afa724ddf1a3a5ff0633edc75c93570b9a5689:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2025-06 ncloc ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 1dadb2aefa8c7e20098f8bdd4fad45383a8ebab7 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 1dadb2aefa8c7e20098f8bdd4fad45383a8ebab7 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show 1dadb2aefa8c7e20098f8bdd4fad45383a8ebab7:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show 1dadb2aefa8c7e20098f8bdd4fad45383a8ebab7:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2025-05 ncloc ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 0525c055fcc6b25297084bdaddc072d206345df1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 0525c055fcc6b25297084bdaddc072d206345df1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show 0525c055fcc6b25297084bdaddc072d206345df1:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show 0525c055fcc6b25297084bdaddc072d206345df1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2025-04 ncloc ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 3cc670ac3860bb9990d89f61d9b1644b0e4c658f | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 3cc670ac3860bb9990d89f61d9b1644b0e4c658f | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show 3cc670ac3860bb9990d89f61d9b1644b0e4c658f:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show 3cc670ac3860bb9990d89f61d9b1644b0e4c658f:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2024-08 ncloc ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 0a6ab2622fd9404afdc60100fef54c3c112ea379 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 0a6ab2622fd9404afdc60100fef54c3c112ea379 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 0a6ab2622fd9404afdc60100fef54c3c112ea379:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 0a6ab2622fd9404afdc60100fef54c3c112ea379:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2025-03 ncloc ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only e59f9382a0de2f70b931373b29a11a27824bf639 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only e59f9382a0de2f70b931373b29a11a27824bf639 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show e59f9382a0de2f70b931373b29a11a27824bf639:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show e59f9382a0de2f70b931373b29a11a27824bf639:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-05 technical_debt ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 947772d66c6d108a7d12fe65b8b76f6110f7d20e | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 947772d66c6d108a7d12fe65b8b76f6110f7d20e | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 947772d66c6d108a7d12fe65b8b76f6110f7d20e:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 947772d66c6d108a7d12fe65b8b76f6110f7d20e:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-06 technical_debt ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b3ea0df4e3b73a6e9e8f8fa57b8c052deb8f3694 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b3ea0df4e3b73a6e9e8f8fa57b8c052deb8f3694 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show b3ea0df4e3b73a6e9e8f8fa57b8c052deb8f3694:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show b3ea0df4e3b73a6e9e8f8fa57b8c052deb8f3694:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-07 technical_debt ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 30a70325d55e110b87a6279664e6b7987ceb2067 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 30a70325d55e110b87a6279664e6b7987ceb2067 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 30a70325d55e110b87a6279664e6b7987ceb2067:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 30a70325d55e110b87a6279664e6b7987ceb2067:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-08 technical_debt ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 47a9542199eda065b82bfefe2f159323621d3d38 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 47a9542199eda065b82bfefe2f159323621d3d38 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 47a9542199eda065b82bfefe2f159323621d3d38:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 47a9542199eda065b82bfefe2f159323621d3d38:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2025-02 ncloc ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only dfe4ba8dad580232e4450903a5d1b239b19f8173 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only dfe4ba8dad580232e4450903a5d1b239b19f8173 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show dfe4ba8dad580232e4450903a5d1b239b19f8173:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show dfe4ba8dad580232e4450903a5d1b239b19f8173:pyproject.toml 2>/dev/null | head -120 || true


echo '=== DataDog/integrations-core 2025-01 technical_debt ==='
git -C '../treatment-repos/DataDog_integrations-core' rev-parse --is-inside-work-tree
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only 82c4055486147402d96748c0abd63de6850e83d1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only 82c4055486147402d96748c0abd63de6850e83d1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/DataDog_integrations-core' show 82c4055486147402d96748c0abd63de6850e83d1:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/DataDog_integrations-core' show 82c4055486147402d96748c0abd63de6850e83d1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== DataDog/integrations-core 2025-02 technical_debt ==='
git -C '../treatment-repos/DataDog_integrations-core' rev-parse --is-inside-work-tree
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only c3628b5ded79e88ab572dfd7bac6e5c1cd91f1d8 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only c3628b5ded79e88ab572dfd7bac6e5c1cd91f1d8 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/DataDog_integrations-core' show c3628b5ded79e88ab572dfd7bac6e5c1cd91f1d8:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/DataDog_integrations-core' show c3628b5ded79e88ab572dfd7bac6e5c1cd91f1d8:pyproject.toml 2>/dev/null | head -120 || true


echo '=== DataDog/integrations-core 2025-03 technical_debt ==='
git -C '../treatment-repos/DataDog_integrations-core' rev-parse --is-inside-work-tree
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only 67cf3ad93e6873944bcdbd153c7305b03c2f51d4 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only 67cf3ad93e6873944bcdbd153c7305b03c2f51d4 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/DataDog_integrations-core' show 67cf3ad93e6873944bcdbd153c7305b03c2f51d4:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/DataDog_integrations-core' show 67cf3ad93e6873944bcdbd153c7305b03c2f51d4:pyproject.toml 2>/dev/null | head -120 || true


echo '=== DataDog/integrations-core 2025-04 technical_debt ==='
git -C '../treatment-repos/DataDog_integrations-core' rev-parse --is-inside-work-tree
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only fe4697fca14149122b2d992e53f8a0396755ebff | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only fe4697fca14149122b2d992e53f8a0396755ebff | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/DataDog_integrations-core' show fe4697fca14149122b2d992e53f8a0396755ebff:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/DataDog_integrations-core' show fe4697fca14149122b2d992e53f8a0396755ebff:pyproject.toml 2>/dev/null | head -120 || true


echo '=== DataDog/integrations-core 2025-07 technical_debt ==='
git -C '../treatment-repos/DataDog_integrations-core' rev-parse --is-inside-work-tree
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only 26abd13d37aca13903e1cf8e64b1f0f0959630f6 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only 26abd13d37aca13903e1cf8e64b1f0f0959630f6 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/DataDog_integrations-core' show 26abd13d37aca13903e1cf8e64b1f0f0959630f6:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/DataDog_integrations-core' show 26abd13d37aca13903e1cf8e64b1f0f0959630f6:pyproject.toml 2>/dev/null | head -120 || true


echo '=== DataDog/integrations-core 2025-08 technical_debt ==='
git -C '../treatment-repos/DataDog_integrations-core' rev-parse --is-inside-work-tree
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only af4afd423a8cce60bcaf879e543f1b696e3f0caa | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only af4afd423a8cce60bcaf879e543f1b696e3f0caa | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/DataDog_integrations-core' show af4afd423a8cce60bcaf879e543f1b696e3f0caa:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/DataDog_integrations-core' show af4afd423a8cce60bcaf879e543f1b696e3f0caa:pyproject.toml 2>/dev/null | head -120 || true


echo '=== DataDog/integrations-core 2024-12 technical_debt ==='
git -C '../treatment-repos/DataDog_integrations-core' rev-parse --is-inside-work-tree
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only e6b077a2f4e4526dc00261698d752e7481547e66 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only e6b077a2f4e4526dc00261698d752e7481547e66 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/DataDog_integrations-core' show e6b077a2f4e4526dc00261698d752e7481547e66:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/DataDog_integrations-core' show e6b077a2f4e4526dc00261698d752e7481547e66:pyproject.toml 2>/dev/null | head -120 || true


echo '=== DataDog/integrations-core 2024-11 technical_debt ==='
git -C '../treatment-repos/DataDog_integrations-core' rev-parse --is-inside-work-tree
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only c08fd423affb8f7257d8fcb8e9a5afd869681415 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only c08fd423affb8f7257d8fcb8e9a5afd869681415 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/DataDog_integrations-core' show c08fd423affb8f7257d8fcb8e9a5afd869681415:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/DataDog_integrations-core' show c08fd423affb8f7257d8fcb8e9a5afd869681415:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2025-01 ncloc ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 5e98b7f4c0cf16cdbab10d945c086a5f9ea4be6c | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 5e98b7f4c0cf16cdbab10d945c086a5f9ea4be6c | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show 5e98b7f4c0cf16cdbab10d945c086a5f9ea4be6c:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show 5e98b7f4c0cf16cdbab10d945c086a5f9ea4be6c:pyproject.toml 2>/dev/null | head -120 || true


echo '=== DataDog/integrations-core 2025-06 technical_debt ==='
git -C '../treatment-repos/DataDog_integrations-core' rev-parse --is-inside-work-tree
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only f9f78ed17fce4bcd63e24aaa39a9e47dddbd7f4f | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only f9f78ed17fce4bcd63e24aaa39a9e47dddbd7f4f | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/DataDog_integrations-core' show f9f78ed17fce4bcd63e24aaa39a9e47dddbd7f4f:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/DataDog_integrations-core' show f9f78ed17fce4bcd63e24aaa39a9e47dddbd7f4f:pyproject.toml 2>/dev/null | head -120 || true


echo '=== DataDog/integrations-core 2025-05 technical_debt ==='
git -C '../treatment-repos/DataDog_integrations-core' rev-parse --is-inside-work-tree
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only 1c924825332db0360a98ffc39e7c9d87618d66aa | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only 1c924825332db0360a98ffc39e7c9d87618d66aa | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/DataDog_integrations-core' show 1c924825332db0360a98ffc39e7c9d87618d66aa:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/DataDog_integrations-core' show 1c924825332db0360a98ffc39e7c9d87618d66aa:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2024-12 ncloc ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 92d845fa725cd044db1a10299046031c201febd0 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 92d845fa725cd044db1a10299046031c201febd0 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show 92d845fa725cd044db1a10299046031c201febd0:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show 92d845fa725cd044db1a10299046031c201febd0:pyproject.toml 2>/dev/null | head -120 || true


echo '=== DataDog/integrations-core 2024-09 technical_debt ==='
git -C '../treatment-repos/DataDog_integrations-core' rev-parse --is-inside-work-tree
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only c1e85309a37c7c508f41c365f3002708f77f8cbf | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only c1e85309a37c7c508f41c365f3002708f77f8cbf | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/DataDog_integrations-core' show c1e85309a37c7c508f41c365f3002708f77f8cbf:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/DataDog_integrations-core' show c1e85309a37c7c508f41c365f3002708f77f8cbf:pyproject.toml 2>/dev/null | head -120 || true


echo '=== DataDog/integrations-core 2024-08 technical_debt ==='
git -C '../treatment-repos/DataDog_integrations-core' rev-parse --is-inside-work-tree
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only 523c5afc8405d8726f7cf8867bbd5f75a75ce24e | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only 523c5afc8405d8726f7cf8867bbd5f75a75ce24e | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/DataDog_integrations-core' show 523c5afc8405d8726f7cf8867bbd5f75a75ce24e:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/DataDog_integrations-core' show 523c5afc8405d8726f7cf8867bbd5f75a75ce24e:pyproject.toml 2>/dev/null | head -120 || true


echo '=== DataDog/integrations-core 2024-07 technical_debt ==='
git -C '../treatment-repos/DataDog_integrations-core' rev-parse --is-inside-work-tree
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only cdbf62d31e3f4f8ab0702b386c32dd06473d95e7 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only cdbf62d31e3f4f8ab0702b386c32dd06473d95e7 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/DataDog_integrations-core' show cdbf62d31e3f4f8ab0702b386c32dd06473d95e7:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/DataDog_integrations-core' show cdbf62d31e3f4f8ab0702b386c32dd06473d95e7:pyproject.toml 2>/dev/null | head -120 || true


echo '=== DataDog/integrations-core 2024-10 technical_debt ==='
git -C '../treatment-repos/DataDog_integrations-core' rev-parse --is-inside-work-tree
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only cbb5fc6a80505309a1b00b37b77d772255490afa | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only cbb5fc6a80505309a1b00b37b77d772255490afa | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/DataDog_integrations-core' show cbb5fc6a80505309a1b00b37b77d772255490afa:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/DataDog_integrations-core' show cbb5fc6a80505309a1b00b37b77d772255490afa:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2024-11 ncloc ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 83e26a231e487673ce6f92dc32e7fe7d8c6d16d0 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 83e26a231e487673ce6f92dc32e7fe7d8c6d16d0 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show 83e26a231e487673ce6f92dc32e7fe7d8c6d16d0:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show 83e26a231e487673ce6f92dc32e7fe7d8c6d16d0:pyproject.toml 2>/dev/null | head -120 || true


echo '=== DataDog/integrations-core 2024-06 technical_debt ==='
git -C '../treatment-repos/DataDog_integrations-core' rev-parse --is-inside-work-tree
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only 40193a9e2b1b854a8f3b95dd0e7041259f22653d | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/DataDog_integrations-core' ls-tree -r --name-only 40193a9e2b1b854a8f3b95dd0e7041259f22653d | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/DataDog_integrations-core' show 40193a9e2b1b854a8f3b95dd0e7041259f22653d:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/DataDog_integrations-core' show 40193a9e2b1b854a8f3b95dd0e7041259f22653d:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2024-10 ncloc ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only f3fc339ef650517674a22995d81f9ae21e7bae5a | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only f3fc339ef650517674a22995d81f9ae21e7bae5a | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show f3fc339ef650517674a22995d81f9ae21e7bae5a:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show f3fc339ef650517674a22995d81f9ae21e7bae5a:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-02 technical_debt ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 4a0c1c874fc3b56c4f2dc400a4367a71df5a66fe | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 4a0c1c874fc3b56c4f2dc400a4367a71df5a66fe | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 4a0c1c874fc3b56c4f2dc400a4367a71df5a66fe:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 4a0c1c874fc3b56c4f2dc400a4367a71df5a66fe:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2024-09 ncloc ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only d6b505477886b48b4868a56481373e2a29a72fcd | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only d6b505477886b48b4868a56481373e2a29a72fcd | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show d6b505477886b48b4868a56481373e2a29a72fcd:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show d6b505477886b48b4868a56481373e2a29a72fcd:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-04 static_analysis_warnings ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 2b8b1a696992e64578f2e4c5fc285e90b60b87a6 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 2b8b1a696992e64578f2e4c5fc285e90b60b87a6 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 2b8b1a696992e64578f2e4c5fc285e90b60b87a6:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 2b8b1a696992e64578f2e4c5fc285e90b60b87a6:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-04 code_smells ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 2b8b1a696992e64578f2e4c5fc285e90b60b87a6 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 2b8b1a696992e64578f2e4c5fc285e90b60b87a6 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 2b8b1a696992e64578f2e4c5fc285e90b60b87a6:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 2b8b1a696992e64578f2e4c5fc285e90b60b87a6:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-02 code_smells ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b71074ef73498f532234a837ea04a08ffbf4e804 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b71074ef73498f532234a837ea04a08ffbf4e804 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show b71074ef73498f532234a837ea04a08ffbf4e804:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show b71074ef73498f532234a837ea04a08ffbf4e804:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-01 code_smells ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 7a540bf3dded6f1e58d32bf21a97d9a5c013afc1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 7a540bf3dded6f1e58d32bf21a97d9a5c013afc1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 7a540bf3dded6f1e58d32bf21a97d9a5c013afc1:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 7a540bf3dded6f1e58d32bf21a97d9a5c013afc1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-03 code_smells ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 745167c81c219beda5ebaf850dfb7a3e772f96ac | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 745167c81c219beda5ebaf850dfb7a3e772f96ac | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 745167c81c219beda5ebaf850dfb7a3e772f96ac:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 745167c81c219beda5ebaf850dfb7a3e772f96ac:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-12 code_smells ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 343dc0da8de0cf2f645cf8b5d76f5b439cb817f3 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 343dc0da8de0cf2f645cf8b5d76f5b439cb817f3 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 343dc0da8de0cf2f645cf8b5d76f5b439cb817f3:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 343dc0da8de0cf2f645cf8b5d76f5b439cb817f3:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-11 code_smells ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 25a633450d1223dcc8f1ad59d260d2e844b5519d | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 25a633450d1223dcc8f1ad59d260d2e844b5519d | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 25a633450d1223dcc8f1ad59d260d2e844b5519d:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 25a633450d1223dcc8f1ad59d260d2e844b5519d:pyproject.toml 2>/dev/null | head -120 || true


echo '=== cgevans/qslib 2025-05 ncloc ==='
git -C '../treatment-repos/cgevans_qslib' rev-parse --is-inside-work-tree
git -C '../treatment-repos/cgevans_qslib' ls-tree -r --name-only d02b38180d3a4f06775d13e613b0f382447d7c6b | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/cgevans_qslib' ls-tree -r --name-only d02b38180d3a4f06775d13e613b0f382447d7c6b | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/cgevans_qslib' show d02b38180d3a4f06775d13e613b0f382447d7c6b:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/cgevans_qslib' show d02b38180d3a4f06775d13e613b0f382447d7c6b:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-04 cognitive_complexity ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 08f147eb9879e899fb7939f4b9413c86164ba7f9 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 08f147eb9879e899fb7939f4b9413c86164ba7f9 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 08f147eb9879e899fb7939f4b9413c86164ba7f9:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 08f147eb9879e899fb7939f4b9413c86164ba7f9:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-02 static_analysis_warnings ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b71074ef73498f532234a837ea04a08ffbf4e804 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b71074ef73498f532234a837ea04a08ffbf4e804 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show b71074ef73498f532234a837ea04a08ffbf4e804:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show b71074ef73498f532234a837ea04a08ffbf4e804:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-01 static_analysis_warnings ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 7a540bf3dded6f1e58d32bf21a97d9a5c013afc1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 7a540bf3dded6f1e58d32bf21a97d9a5c013afc1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 7a540bf3dded6f1e58d32bf21a97d9a5c013afc1:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 7a540bf3dded6f1e58d32bf21a97d9a5c013afc1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-03 static_analysis_warnings ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 745167c81c219beda5ebaf850dfb7a3e772f96ac | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 745167c81c219beda5ebaf850dfb7a3e772f96ac | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 745167c81c219beda5ebaf850dfb7a3e772f96ac:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 745167c81c219beda5ebaf850dfb7a3e772f96ac:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-12 static_analysis_warnings ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 343dc0da8de0cf2f645cf8b5d76f5b439cb817f3 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 343dc0da8de0cf2f645cf8b5d76f5b439cb817f3 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 343dc0da8de0cf2f645cf8b5d76f5b439cb817f3:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 343dc0da8de0cf2f645cf8b5d76f5b439cb817f3:pyproject.toml 2>/dev/null | head -120 || true


echo '=== cgevans/qslib 2025-08 ncloc ==='
git -C '../treatment-repos/cgevans_qslib' rev-parse --is-inside-work-tree
git -C '../treatment-repos/cgevans_qslib' ls-tree -r --name-only 8f7d15ae779d1e4381e4fe9cdbec6871a0e43678 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/cgevans_qslib' ls-tree -r --name-only 8f7d15ae779d1e4381e4fe9cdbec6871a0e43678 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/cgevans_qslib' show 8f7d15ae779d1e4381e4fe9cdbec6871a0e43678:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/cgevans_qslib' show 8f7d15ae779d1e4381e4fe9cdbec6871a0e43678:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-11 static_analysis_warnings ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 25a633450d1223dcc8f1ad59d260d2e844b5519d | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 25a633450d1223dcc8f1ad59d260d2e844b5519d | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 25a633450d1223dcc8f1ad59d260d2e844b5519d:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 25a633450d1223dcc8f1ad59d260d2e844b5519d:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-08 cognitive_complexity ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 79cf381322842888a721905c09490e85f98a5a2a | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 79cf381322842888a721905c09490e85f98a5a2a | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 79cf381322842888a721905c09490e85f98a5a2a:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 79cf381322842888a721905c09490e85f98a5a2a:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-05 code_smells ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 947772d66c6d108a7d12fe65b8b76f6110f7d20e | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 947772d66c6d108a7d12fe65b8b76f6110f7d20e | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 947772d66c6d108a7d12fe65b8b76f6110f7d20e:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 947772d66c6d108a7d12fe65b8b76f6110f7d20e:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-08 code_smells ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 47a9542199eda065b82bfefe2f159323621d3d38 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 47a9542199eda065b82bfefe2f159323621d3d38 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 47a9542199eda065b82bfefe2f159323621d3d38:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 47a9542199eda065b82bfefe2f159323621d3d38:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-07 code_smells ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 30a70325d55e110b87a6279664e6b7987ceb2067 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 30a70325d55e110b87a6279664e6b7987ceb2067 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 30a70325d55e110b87a6279664e6b7987ceb2067:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 30a70325d55e110b87a6279664e6b7987ceb2067:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-06 code_smells ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b3ea0df4e3b73a6e9e8f8fa57b8c052deb8f3694 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b3ea0df4e3b73a6e9e8f8fa57b8c052deb8f3694 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show b3ea0df4e3b73a6e9e8f8fa57b8c052deb8f3694:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show b3ea0df4e3b73a6e9e8f8fa57b8c052deb8f3694:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-04 bugs ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 2b8b1a696992e64578f2e4c5fc285e90b60b87a6 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 2b8b1a696992e64578f2e4c5fc285e90b60b87a6 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 2b8b1a696992e64578f2e4c5fc285e90b60b87a6:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 2b8b1a696992e64578f2e4c5fc285e90b60b87a6:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-07 cognitive_complexity ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0:pyproject.toml 2>/dev/null | head -120 || true


echo '=== ysj9909/SHViT 2024-04 technical_debt ==='
git -C '../control-repos/ysj9909_SHViT' rev-parse --is-inside-work-tree
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only fee7ce4258e81baf9e929e90f26168d632d186a7 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only fee7ce4258e81baf9e929e90f26168d632d186a7 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/ysj9909_SHViT' show fee7ce4258e81baf9e929e90f26168d632d186a7:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/ysj9909_SHViT' show fee7ce4258e81baf9e929e90f26168d632d186a7:pyproject.toml 2>/dev/null | head -120 || true


echo '=== ysj9909/SHViT 2024-05 technical_debt ==='
git -C '../control-repos/ysj9909_SHViT' rev-parse --is-inside-work-tree
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only 20819cb8f624e183b1fa2ce941ed18ab8037b07d | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only 20819cb8f624e183b1fa2ce941ed18ab8037b07d | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/ysj9909_SHViT' show 20819cb8f624e183b1fa2ce941ed18ab8037b07d:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/ysj9909_SHViT' show 20819cb8f624e183b1fa2ce941ed18ab8037b07d:pyproject.toml 2>/dev/null | head -120 || true


echo '=== ysj9909/SHViT 2024-06 technical_debt ==='
git -C '../control-repos/ysj9909_SHViT' rev-parse --is-inside-work-tree
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only 6a729ccf18e0b941714b529638bd3d9bacebcef0 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only 6a729ccf18e0b941714b529638bd3d9bacebcef0 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/ysj9909_SHViT' show 6a729ccf18e0b941714b529638bd3d9bacebcef0:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/ysj9909_SHViT' show 6a729ccf18e0b941714b529638bd3d9bacebcef0:pyproject.toml 2>/dev/null | head -120 || true


echo '=== whiteducksoftware/flock 2025-06 ncloc ==='
git -C '../treatment-repos/whiteducksoftware_flock' rev-parse --is-inside-work-tree
git -C '../treatment-repos/whiteducksoftware_flock' ls-tree -r --name-only db5e65e61bdb943cae439f796be085c5a8218a3c | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/whiteducksoftware_flock' ls-tree -r --name-only db5e65e61bdb943cae439f796be085c5a8218a3c | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/whiteducksoftware_flock' show db5e65e61bdb943cae439f796be085c5a8218a3c:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/whiteducksoftware_flock' show db5e65e61bdb943cae439f796be085c5a8218a3c:pyproject.toml 2>/dev/null | head -120 || true


echo '=== whiteducksoftware/flock 2025-05 ncloc ==='
git -C '../treatment-repos/whiteducksoftware_flock' rev-parse --is-inside-work-tree
git -C '../treatment-repos/whiteducksoftware_flock' ls-tree -r --name-only c60e12a13b66d7f9b7c92f42c2681e331c8ed31d | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/whiteducksoftware_flock' ls-tree -r --name-only c60e12a13b66d7f9b7c92f42c2681e331c8ed31d | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/whiteducksoftware_flock' show c60e12a13b66d7f9b7c92f42c2681e331c8ed31d:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/whiteducksoftware_flock' show c60e12a13b66d7f9b7c92f42c2681e331c8ed31d:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-06 cognitive_complexity ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only bf87ddcb0e02027bb8c1e7a1aa2e03f0c4312e90 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only bf87ddcb0e02027bb8c1e7a1aa2e03f0c4312e90 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show bf87ddcb0e02027bb8c1e7a1aa2e03f0c4312e90:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show bf87ddcb0e02027bb8c1e7a1aa2e03f0c4312e90:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zhipeixu/FakeShield 2025-02 technical_debt ==='
git -C '../control-repos/zhipeixu_FakeShield' rev-parse --is-inside-work-tree
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only b807b92ac958678bb278e741864ba4b821fb73c1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only b807b92ac958678bb278e741864ba4b821fb73c1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/zhipeixu_FakeShield' show b807b92ac958678bb278e741864ba4b821fb73c1:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/zhipeixu_FakeShield' show b807b92ac958678bb278e741864ba4b821fb73c1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zhipeixu/FakeShield 2025-04 technical_debt ==='
git -C '../control-repos/zhipeixu_FakeShield' rev-parse --is-inside-work-tree
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 2910fb826ea20e11c2c2553c36984630216c0bab | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 2910fb826ea20e11c2c2553c36984630216c0bab | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/zhipeixu_FakeShield' show 2910fb826ea20e11c2c2553c36984630216c0bab:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/zhipeixu_FakeShield' show 2910fb826ea20e11c2c2553c36984630216c0bab:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zhipeixu/FakeShield 2025-06 technical_debt ==='
git -C '../control-repos/zhipeixu_FakeShield' rev-parse --is-inside-work-tree
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 346cb6c74c9a426c1c00d98b13e5f417161a94c1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 346cb6c74c9a426c1c00d98b13e5f417161a94c1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/zhipeixu_FakeShield' show 346cb6c74c9a426c1c00d98b13e5f417161a94c1:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/zhipeixu_FakeShield' show 346cb6c74c9a426c1c00d98b13e5f417161a94c1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zhipeixu/FakeShield 2025-05 technical_debt ==='
git -C '../control-repos/zhipeixu_FakeShield' rev-parse --is-inside-work-tree
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only c34dab9b8df3dc77d2632344eb0d0af387d0658f | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only c34dab9b8df3dc77d2632344eb0d0af387d0658f | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/zhipeixu_FakeShield' show c34dab9b8df3dc77d2632344eb0d0af387d0658f:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/zhipeixu_FakeShield' show c34dab9b8df3dc77d2632344eb0d0af387d0658f:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zhipeixu/FakeShield 2025-03 technical_debt ==='
git -C '../control-repos/zhipeixu_FakeShield' rev-parse --is-inside-work-tree
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 7bd43c8badef7341807e85e55a8b216dac6c2424 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 7bd43c8badef7341807e85e55a8b216dac6c2424 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/zhipeixu_FakeShield' show 7bd43c8badef7341807e85e55a8b216dac6c2424:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/zhipeixu_FakeShield' show 7bd43c8badef7341807e85e55a8b216dac6c2424:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-07 code_smells ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b0bc2078fb1e70607879d82ce96e3a488bc41f69 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b0bc2078fb1e70607879d82ce96e3a488bc41f69 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show b0bc2078fb1e70607879d82ce96e3a488bc41f69:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show b0bc2078fb1e70607879d82ce96e3a488bc41f69:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-06 code_smells ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 462af82d7027979fe68e7245b772c2c6cdbe7d94 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 462af82d7027979fe68e7245b772c2c6cdbe7d94 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 462af82d7027979fe68e7245b772c2c6cdbe7d94:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 462af82d7027979fe68e7245b772c2c6cdbe7d94:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-05 code_smells ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 92a0cf0fdaee28ffba8329483e55f2a5d5c529fe | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 92a0cf0fdaee28ffba8329483e55f2a5d5c529fe | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 92a0cf0fdaee28ffba8329483e55f2a5d5c529fe:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 92a0cf0fdaee28ffba8329483e55f2a5d5c529fe:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-04 code_smells ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 1bce2bad367d5baf842badb51a0d78c8543a49ef | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 1bce2bad367d5baf842badb51a0d78c8543a49ef | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 1bce2bad367d5baf842badb51a0d78c8543a49ef:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 1bce2bad367d5baf842badb51a0d78c8543a49ef:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-03 code_smells ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only fff7b27eea91bf2b3d3f3080f0919c3ac62978b8 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only fff7b27eea91bf2b3d3f3080f0919c3ac62978b8 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show fff7b27eea91bf2b3d3f3080f0919c3ac62978b8:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show fff7b27eea91bf2b3d3f3080f0919c3ac62978b8:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-02 code_smells ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 4a0c1c874fc3b56c4f2dc400a4367a71df5a66fe | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 4a0c1c874fc3b56c4f2dc400a4367a71df5a66fe | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 4a0c1c874fc3b56c4f2dc400a4367a71df5a66fe:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 4a0c1c874fc3b56c4f2dc400a4367a71df5a66fe:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-01 code_smells ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only f4c57a962f8cc96085eb41860c1346da77228824 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only f4c57a962f8cc96085eb41860c1346da77228824 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show f4c57a962f8cc96085eb41860c1346da77228824:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show f4c57a962f8cc96085eb41860c1346da77228824:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-05 cognitive_complexity ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only fa2cab6b204f2efeabb5c5bbc1d35ff23c91ec8b | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only fa2cab6b204f2efeabb5c5bbc1d35ff23c91ec8b | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show fa2cab6b204f2efeabb5c5bbc1d35ff23c91ec8b:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show fa2cab6b204f2efeabb5c5bbc1d35ff23c91ec8b:pyproject.toml 2>/dev/null | head -120 || true


echo '=== whiteducksoftware/flock 2025-08 ncloc ==='
git -C '../treatment-repos/whiteducksoftware_flock' rev-parse --is-inside-work-tree
git -C '../treatment-repos/whiteducksoftware_flock' ls-tree -r --name-only 88b363080e95e8bdd87e32924216febb6cb5e4c7 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/whiteducksoftware_flock' ls-tree -r --name-only 88b363080e95e8bdd87e32924216febb6cb5e4c7 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/whiteducksoftware_flock' show 88b363080e95e8bdd87e32924216febb6cb5e4c7:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/whiteducksoftware_flock' show 88b363080e95e8bdd87e32924216febb6cb5e4c7:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-03 cognitive_complexity ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only ecdaddcfaf15967165806e2cd4f9bc0cfb40f0e1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only ecdaddcfaf15967165806e2cd4f9bc0cfb40f0e1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show ecdaddcfaf15967165806e2cd4f9bc0cfb40f0e1:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show ecdaddcfaf15967165806e2cd4f9bc0cfb40f0e1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-04 static_analysis_warnings ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 08f147eb9879e899fb7939f4b9413c86164ba7f9 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 08f147eb9879e899fb7939f4b9413c86164ba7f9 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 08f147eb9879e899fb7939f4b9413c86164ba7f9:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 08f147eb9879e899fb7939f4b9413c86164ba7f9:pyproject.toml 2>/dev/null | head -120 || true


echo '=== getsentry/sentry 2025-02 code_smells ==='
git -C '../treatment-repos/getsentry_sentry' rev-parse --is-inside-work-tree
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only c4502d06cff34abeb8f58810743fb907ee914348 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only c4502d06cff34abeb8f58810743fb907ee914348 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/getsentry_sentry' show c4502d06cff34abeb8f58810743fb907ee914348:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/getsentry_sentry' show c4502d06cff34abeb8f58810743fb907ee914348:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-04 code_smells ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 08f147eb9879e899fb7939f4b9413c86164ba7f9 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 08f147eb9879e899fb7939f4b9413c86164ba7f9 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 08f147eb9879e899fb7939f4b9413c86164ba7f9:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 08f147eb9879e899fb7939f4b9413c86164ba7f9:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-11 bugs ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 25a633450d1223dcc8f1ad59d260d2e844b5519d | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 25a633450d1223dcc8f1ad59d260d2e844b5519d | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 25a633450d1223dcc8f1ad59d260d2e844b5519d:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 25a633450d1223dcc8f1ad59d260d2e844b5519d:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-03 bugs ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 745167c81c219beda5ebaf850dfb7a3e772f96ac | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 745167c81c219beda5ebaf850dfb7a3e772f96ac | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 745167c81c219beda5ebaf850dfb7a3e772f96ac:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 745167c81c219beda5ebaf850dfb7a3e772f96ac:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-01 bugs ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 7a540bf3dded6f1e58d32bf21a97d9a5c013afc1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 7a540bf3dded6f1e58d32bf21a97d9a5c013afc1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 7a540bf3dded6f1e58d32bf21a97d9a5c013afc1:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 7a540bf3dded6f1e58d32bf21a97d9a5c013afc1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-02 bugs ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b71074ef73498f532234a837ea04a08ffbf4e804 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b71074ef73498f532234a837ea04a08ffbf4e804 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show b71074ef73498f532234a837ea04a08ffbf4e804:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show b71074ef73498f532234a837ea04a08ffbf4e804:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-12 bugs ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 343dc0da8de0cf2f645cf8b5d76f5b439cb817f3 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 343dc0da8de0cf2f645cf8b5d76f5b439cb817f3 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 343dc0da8de0cf2f645cf8b5d76f5b439cb817f3:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 343dc0da8de0cf2f645cf8b5d76f5b439cb817f3:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-08 bugs ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 47a9542199eda065b82bfefe2f159323621d3d38 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 47a9542199eda065b82bfefe2f159323621d3d38 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 47a9542199eda065b82bfefe2f159323621d3d38:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 47a9542199eda065b82bfefe2f159323621d3d38:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-06 bugs ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b3ea0df4e3b73a6e9e8f8fa57b8c052deb8f3694 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b3ea0df4e3b73a6e9e8f8fa57b8c052deb8f3694 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show b3ea0df4e3b73a6e9e8f8fa57b8c052deb8f3694:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show b3ea0df4e3b73a6e9e8f8fa57b8c052deb8f3694:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-07 bugs ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 30a70325d55e110b87a6279664e6b7987ceb2067 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 30a70325d55e110b87a6279664e6b7987ceb2067 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 30a70325d55e110b87a6279664e6b7987ceb2067:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 30a70325d55e110b87a6279664e6b7987ceb2067:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-05 bugs ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 947772d66c6d108a7d12fe65b8b76f6110f7d20e | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 947772d66c6d108a7d12fe65b8b76f6110f7d20e | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 947772d66c6d108a7d12fe65b8b76f6110f7d20e:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 947772d66c6d108a7d12fe65b8b76f6110f7d20e:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-05 static_analysis_warnings ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 947772d66c6d108a7d12fe65b8b76f6110f7d20e | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 947772d66c6d108a7d12fe65b8b76f6110f7d20e | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 947772d66c6d108a7d12fe65b8b76f6110f7d20e:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 947772d66c6d108a7d12fe65b8b76f6110f7d20e:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-07 static_analysis_warnings ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 30a70325d55e110b87a6279664e6b7987ceb2067 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 30a70325d55e110b87a6279664e6b7987ceb2067 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 30a70325d55e110b87a6279664e6b7987ceb2067:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 30a70325d55e110b87a6279664e6b7987ceb2067:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-08 static_analysis_warnings ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 47a9542199eda065b82bfefe2f159323621d3d38 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 47a9542199eda065b82bfefe2f159323621d3d38 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 47a9542199eda065b82bfefe2f159323621d3d38:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 47a9542199eda065b82bfefe2f159323621d3d38:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2025-06 static_analysis_warnings ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b3ea0df4e3b73a6e9e8f8fa57b8c052deb8f3694 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b3ea0df4e3b73a6e9e8f8fa57b8c052deb8f3694 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show b3ea0df4e3b73a6e9e8f8fa57b8c052deb8f3694:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show b3ea0df4e3b73a6e9e8f8fa57b8c052deb8f3694:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-05 static_analysis_warnings ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only fa2cab6b204f2efeabb5c5bbc1d35ff23c91ec8b | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only fa2cab6b204f2efeabb5c5bbc1d35ff23c91ec8b | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show fa2cab6b204f2efeabb5c5bbc1d35ff23c91ec8b:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show fa2cab6b204f2efeabb5c5bbc1d35ff23c91ec8b:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-08 technical_debt ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 0150699ff9adda89142bf65e2600619d61f6d55a | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 0150699ff9adda89142bf65e2600619d61f6d55a | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show 0150699ff9adda89142bf65e2600619d61f6d55a:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show 0150699ff9adda89142bf65e2600619d61f6d55a:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-05 code_smells ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only fa2cab6b204f2efeabb5c5bbc1d35ff23c91ec8b | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only fa2cab6b204f2efeabb5c5bbc1d35ff23c91ec8b | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show fa2cab6b204f2efeabb5c5bbc1d35ff23c91ec8b:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show fa2cab6b204f2efeabb5c5bbc1d35ff23c91ec8b:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-02 cognitive_complexity ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only e6cdfed56138f74a1e8bcac05f60036d96ab9a6a | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only e6cdfed56138f74a1e8bcac05f60036d96ab9a6a | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show e6cdfed56138f74a1e8bcac05f60036d96ab9a6a:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show e6cdfed56138f74a1e8bcac05f60036d96ab9a6a:pyproject.toml 2>/dev/null | head -120 || true


echo '=== getsentry/sentry 2025-02 static_analysis_warnings ==='
git -C '../treatment-repos/getsentry_sentry' rev-parse --is-inside-work-tree
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only c4502d06cff34abeb8f58810743fb907ee914348 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only c4502d06cff34abeb8f58810743fb907ee914348 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/getsentry_sentry' show c4502d06cff34abeb8f58810743fb907ee914348:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/getsentry_sentry' show c4502d06cff34abeb8f58810743fb907ee914348:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-07 technical_debt ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 4f4b01a142d5224279c4d0fcd6b944fcc80b343b | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 4f4b01a142d5224279c4d0fcd6b944fcc80b343b | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show 4f4b01a142d5224279c4d0fcd6b944fcc80b343b:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show 4f4b01a142d5224279c4d0fcd6b944fcc80b343b:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-06 technical_debt ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only f43af48a983a734ca863a04362b99176d506bcb8 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only f43af48a983a734ca863a04362b99176d506bcb8 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show f43af48a983a734ca863a04362b99176d506bcb8:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show f43af48a983a734ca863a04362b99176d506bcb8:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-03 static_analysis_warnings ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only ecdaddcfaf15967165806e2cd4f9bc0cfb40f0e1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only ecdaddcfaf15967165806e2cd4f9bc0cfb40f0e1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show ecdaddcfaf15967165806e2cd4f9bc0cfb40f0e1:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show ecdaddcfaf15967165806e2cd4f9bc0cfb40f0e1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-06 bugs ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 462af82d7027979fe68e7245b772c2c6cdbe7d94 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 462af82d7027979fe68e7245b772c2c6cdbe7d94 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 462af82d7027979fe68e7245b772c2c6cdbe7d94:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 462af82d7027979fe68e7245b772c2c6cdbe7d94:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-04 bugs ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 1bce2bad367d5baf842badb51a0d78c8543a49ef | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 1bce2bad367d5baf842badb51a0d78c8543a49ef | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 1bce2bad367d5baf842badb51a0d78c8543a49ef:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 1bce2bad367d5baf842badb51a0d78c8543a49ef:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-01 bugs ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only f4c57a962f8cc96085eb41860c1346da77228824 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only f4c57a962f8cc96085eb41860c1346da77228824 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show f4c57a962f8cc96085eb41860c1346da77228824:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show f4c57a962f8cc96085eb41860c1346da77228824:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-05 bugs ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 92a0cf0fdaee28ffba8329483e55f2a5d5c529fe | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 92a0cf0fdaee28ffba8329483e55f2a5d5c529fe | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 92a0cf0fdaee28ffba8329483e55f2a5d5c529fe:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 92a0cf0fdaee28ffba8329483e55f2a5d5c529fe:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-02 bugs ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 4a0c1c874fc3b56c4f2dc400a4367a71df5a66fe | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 4a0c1c874fc3b56c4f2dc400a4367a71df5a66fe | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 4a0c1c874fc3b56c4f2dc400a4367a71df5a66fe:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 4a0c1c874fc3b56c4f2dc400a4367a71df5a66fe:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-07 bugs ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b0bc2078fb1e70607879d82ce96e3a488bc41f69 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b0bc2078fb1e70607879d82ce96e3a488bc41f69 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show b0bc2078fb1e70607879d82ce96e3a488bc41f69:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show b0bc2078fb1e70607879d82ce96e3a488bc41f69:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-03 bugs ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only fff7b27eea91bf2b3d3f3080f0919c3ac62978b8 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only fff7b27eea91bf2b3d3f3080f0919c3ac62978b8 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show fff7b27eea91bf2b3d3f3080f0919c3ac62978b8:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show fff7b27eea91bf2b3d3f3080f0919c3ac62978b8:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-03 code_smells ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only ecdaddcfaf15967165806e2cd4f9bc0cfb40f0e1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only ecdaddcfaf15967165806e2cd4f9bc0cfb40f0e1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show ecdaddcfaf15967165806e2cd4f9bc0cfb40f0e1:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show ecdaddcfaf15967165806e2cd4f9bc0cfb40f0e1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-02 static_analysis_warnings ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only e6cdfed56138f74a1e8bcac05f60036d96ab9a6a | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only e6cdfed56138f74a1e8bcac05f60036d96ab9a6a | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show e6cdfed56138f74a1e8bcac05f60036d96ab9a6a:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show e6cdfed56138f74a1e8bcac05f60036d96ab9a6a:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-02 code_smells ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only e6cdfed56138f74a1e8bcac05f60036d96ab9a6a | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only e6cdfed56138f74a1e8bcac05f60036d96ab9a6a | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show e6cdfed56138f74a1e8bcac05f60036d96ab9a6a:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show e6cdfed56138f74a1e8bcac05f60036d96ab9a6a:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-07 static_analysis_warnings ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b0bc2078fb1e70607879d82ce96e3a488bc41f69 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only b0bc2078fb1e70607879d82ce96e3a488bc41f69 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show b0bc2078fb1e70607879d82ce96e3a488bc41f69:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show b0bc2078fb1e70607879d82ce96e3a488bc41f69:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-06 static_analysis_warnings ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 462af82d7027979fe68e7245b772c2c6cdbe7d94 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 462af82d7027979fe68e7245b772c2c6cdbe7d94 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 462af82d7027979fe68e7245b772c2c6cdbe7d94:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 462af82d7027979fe68e7245b772c2c6cdbe7d94:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-08 code_smells ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 79cf381322842888a721905c09490e85f98a5a2a | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 79cf381322842888a721905c09490e85f98a5a2a | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 79cf381322842888a721905c09490e85f98a5a2a:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 79cf381322842888a721905c09490e85f98a5a2a:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-05 static_analysis_warnings ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 92a0cf0fdaee28ffba8329483e55f2a5d5c529fe | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 92a0cf0fdaee28ffba8329483e55f2a5d5c529fe | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 92a0cf0fdaee28ffba8329483e55f2a5d5c529fe:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 92a0cf0fdaee28ffba8329483e55f2a5d5c529fe:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-04 static_analysis_warnings ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 1bce2bad367d5baf842badb51a0d78c8543a49ef | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 1bce2bad367d5baf842badb51a0d78c8543a49ef | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 1bce2bad367d5baf842badb51a0d78c8543a49ef:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 1bce2bad367d5baf842badb51a0d78c8543a49ef:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-03 static_analysis_warnings ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only fff7b27eea91bf2b3d3f3080f0919c3ac62978b8 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only fff7b27eea91bf2b3d3f3080f0919c3ac62978b8 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show fff7b27eea91bf2b3d3f3080f0919c3ac62978b8:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show fff7b27eea91bf2b3d3f3080f0919c3ac62978b8:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-08 static_analysis_warnings ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 79cf381322842888a721905c09490e85f98a5a2a | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 79cf381322842888a721905c09490e85f98a5a2a | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 79cf381322842888a721905c09490e85f98a5a2a:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 79cf381322842888a721905c09490e85f98a5a2a:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-05 technical_debt ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 06db0834814629bbac4bea9188101898cc4b0a91 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 06db0834814629bbac4bea9188101898cc4b0a91 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show 06db0834814629bbac4bea9188101898cc4b0a91:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show 06db0834814629bbac4bea9188101898cc4b0a91:pyproject.toml 2>/dev/null | head -120 || true


echo '=== getsentry/sentry 2024-01 code_smells ==='
git -C '../treatment-repos/getsentry_sentry' rev-parse --is-inside-work-tree
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only 8073feb6eac31a856f6a389a1c289430b35e3589 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only 8073feb6eac31a856f6a389a1c289430b35e3589 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/getsentry_sentry' show 8073feb6eac31a856f6a389a1c289430b35e3589:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/getsentry_sentry' show 8073feb6eac31a856f6a389a1c289430b35e3589:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-02 static_analysis_warnings ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 4a0c1c874fc3b56c4f2dc400a4367a71df5a66fe | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only 4a0c1c874fc3b56c4f2dc400a4367a71df5a66fe | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show 4a0c1c874fc3b56c4f2dc400a4367a71df5a66fe:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show 4a0c1c874fc3b56c4f2dc400a4367a71df5a66fe:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-01 static_analysis_warnings ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 1253d960c415d65583dac034353702ad74016da1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 1253d960c415d65583dac034353702ad74016da1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 1253d960c415d65583dac034353702ad74016da1:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 1253d960c415d65583dac034353702ad74016da1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-01 cognitive_complexity ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 1253d960c415d65583dac034353702ad74016da1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 1253d960c415d65583dac034353702ad74016da1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 1253d960c415d65583dac034353702ad74016da1:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 1253d960c415d65583dac034353702ad74016da1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-07 static_analysis_warnings ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-07 code_smells ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0:pyproject.toml 2>/dev/null | head -120 || true


echo '=== getsentry/sentry 2025-06 code_smells ==='
git -C '../treatment-repos/getsentry_sentry' rev-parse --is-inside-work-tree
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only 4f2be477198bf2814c6d6cd4b80ba19cbe386908 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only 4f2be477198bf2814c6d6cd4b80ba19cbe386908 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/getsentry_sentry' show 4f2be477198bf2814c6d6cd4b80ba19cbe386908:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/getsentry_sentry' show 4f2be477198bf2814c6d6cd4b80ba19cbe386908:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-03 technical_debt ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only d5329df09ed618392f858c17160e1d7833a2588c | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only d5329df09ed618392f858c17160e1d7833a2588c | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show d5329df09ed618392f858c17160e1d7833a2588c:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show d5329df09ed618392f858c17160e1d7833a2588c:pyproject.toml 2>/dev/null | head -120 || true


echo '=== getsentry/sentry 2025-01 code_smells ==='
git -C '../treatment-repos/getsentry_sentry' rev-parse --is-inside-work-tree
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only d210118fce94310ef5858d51efe16ee26c995a48 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only d210118fce94310ef5858d51efe16ee26c995a48 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/getsentry_sentry' show d210118fce94310ef5858d51efe16ee26c995a48:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/getsentry_sentry' show d210118fce94310ef5858d51efe16ee26c995a48:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-02 technical_debt ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only f4f4105451484b80b4fb3f71dc41ff395c188cce | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only f4f4105451484b80b4fb3f71dc41ff395c188cce | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show f4f4105451484b80b4fb3f71dc41ff395c188cce:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show f4f4105451484b80b4fb3f71dc41ff395c188cce:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-06 static_analysis_warnings ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only bf87ddcb0e02027bb8c1e7a1aa2e03f0c4312e90 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only bf87ddcb0e02027bb8c1e7a1aa2e03f0c4312e90 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show bf87ddcb0e02027bb8c1e7a1aa2e03f0c4312e90:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show bf87ddcb0e02027bb8c1e7a1aa2e03f0c4312e90:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-01 technical_debt ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only d7391b2a18820e80af59095204f668f1758e2278 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only d7391b2a18820e80af59095204f668f1758e2278 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show d7391b2a18820e80af59095204f668f1758e2278:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show d7391b2a18820e80af59095204f668f1758e2278:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zauberzeug/nicegui 2024-01 static_analysis_warnings ==='
git -C '../treatment-repos/zauberzeug_nicegui' rev-parse --is-inside-work-tree
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only f4c57a962f8cc96085eb41860c1346da77228824 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/zauberzeug_nicegui' ls-tree -r --name-only f4c57a962f8cc96085eb41860c1346da77228824 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/zauberzeug_nicegui' show f4c57a962f8cc96085eb41860c1346da77228824:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/zauberzeug_nicegui' show f4c57a962f8cc96085eb41860c1346da77228824:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2024-12 cognitive_complexity ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 3aa25f3257f981db0b7e8b5411dc209b66c6f4c2 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 3aa25f3257f981db0b7e8b5411dc209b66c6f4c2 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 3aa25f3257f981db0b7e8b5411dc209b66c6f4c2:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 3aa25f3257f981db0b7e8b5411dc209b66c6f4c2:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2024-11 cognitive_complexity ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only b4d51e3b746e6174a7d60c525ea22387f00dcafe | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only b4d51e3b746e6174a7d60c525ea22387f00dcafe | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show b4d51e3b746e6174a7d60c525ea22387f00dcafe:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show b4d51e3b746e6174a7d60c525ea22387f00dcafe:pyproject.toml 2>/dev/null | head -120 || true


echo '=== cgevans/qslib 2025-05 cognitive_complexity ==='
git -C '../treatment-repos/cgevans_qslib' rev-parse --is-inside-work-tree
git -C '../treatment-repos/cgevans_qslib' ls-tree -r --name-only d02b38180d3a4f06775d13e613b0f382447d7c6b | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/cgevans_qslib' ls-tree -r --name-only d02b38180d3a4f06775d13e613b0f382447d7c6b | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/cgevans_qslib' show d02b38180d3a4f06775d13e613b0f382447d7c6b:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/cgevans_qslib' show d02b38180d3a4f06775d13e613b0f382447d7c6b:pyproject.toml 2>/dev/null | head -120 || true


echo '=== getsentry/sentry 2024-01 static_analysis_warnings ==='
git -C '../treatment-repos/getsentry_sentry' rev-parse --is-inside-work-tree
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only 8073feb6eac31a856f6a389a1c289430b35e3589 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only 8073feb6eac31a856f6a389a1c289430b35e3589 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/getsentry_sentry' show 8073feb6eac31a856f6a389a1c289430b35e3589:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/getsentry_sentry' show 8073feb6eac31a856f6a389a1c289430b35e3589:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2024-10 cognitive_complexity ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 12ff477551dfc5a197aca3006e14e4193183dbd8 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 12ff477551dfc5a197aca3006e14e4193183dbd8 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 12ff477551dfc5a197aca3006e14e4193183dbd8:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 12ff477551dfc5a197aca3006e14e4193183dbd8:pyproject.toml 2>/dev/null | head -120 || true


echo '=== cgevans/qslib 2025-05 technical_debt ==='
git -C '../treatment-repos/cgevans_qslib' rev-parse --is-inside-work-tree
git -C '../treatment-repos/cgevans_qslib' ls-tree -r --name-only d02b38180d3a4f06775d13e613b0f382447d7c6b | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/cgevans_qslib' ls-tree -r --name-only d02b38180d3a4f06775d13e613b0f382447d7c6b | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/cgevans_qslib' show d02b38180d3a4f06775d13e613b0f382447d7c6b:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/cgevans_qslib' show d02b38180d3a4f06775d13e613b0f382447d7c6b:pyproject.toml 2>/dev/null | head -120 || true


echo '=== cgevans/qslib 2025-02 cognitive_complexity ==='
git -C '../treatment-repos/cgevans_qslib' rev-parse --is-inside-work-tree
git -C '../treatment-repos/cgevans_qslib' ls-tree -r --name-only f231361a93b274928e71ff2cb06bee91e0bb2c11 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/cgevans_qslib' ls-tree -r --name-only f231361a93b274928e71ff2cb06bee91e0bb2c11 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/cgevans_qslib' show f231361a93b274928e71ff2cb06bee91e0bb2c11:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/cgevans_qslib' show f231361a93b274928e71ff2cb06bee91e0bb2c11:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2025-06 cognitive_complexity ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 1dadb2aefa8c7e20098f8bdd4fad45383a8ebab7 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 1dadb2aefa8c7e20098f8bdd4fad45383a8ebab7 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show 1dadb2aefa8c7e20098f8bdd4fad45383a8ebab7:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show 1dadb2aefa8c7e20098f8bdd4fad45383a8ebab7:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2025-07 cognitive_complexity ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only c7afa724ddf1a3a5ff0633edc75c93570b9a5689 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only c7afa724ddf1a3a5ff0633edc75c93570b9a5689 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show c7afa724ddf1a3a5ff0633edc75c93570b9a5689:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show c7afa724ddf1a3a5ff0633edc75c93570b9a5689:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2025-05 cognitive_complexity ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 0525c055fcc6b25297084bdaddc072d206345df1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 0525c055fcc6b25297084bdaddc072d206345df1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show 0525c055fcc6b25297084bdaddc072d206345df1:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show 0525c055fcc6b25297084bdaddc072d206345df1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2025-08 cognitive_complexity ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 47747287b616d4a2f1dd14f811f218e3caee7f8d | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 47747287b616d4a2f1dd14f811f218e3caee7f8d | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show 47747287b616d4a2f1dd14f811f218e3caee7f8d:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show 47747287b616d4a2f1dd14f811f218e3caee7f8d:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2025-04 cognitive_complexity ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 3cc670ac3860bb9990d89f61d9b1644b0e4c658f | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only 3cc670ac3860bb9990d89f61d9b1644b0e4c658f | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show 3cc670ac3860bb9990d89f61d9b1644b0e4c658f:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show 3cc670ac3860bb9990d89f61d9b1644b0e4c658f:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2024-09 cognitive_complexity ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 761c6ce0ab4db14ddede62cb61b6d6854dff7ea7 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 761c6ce0ab4db14ddede62cb61b6d6854dff7ea7 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 761c6ce0ab4db14ddede62cb61b6d6854dff7ea7:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 761c6ce0ab4db14ddede62cb61b6d6854dff7ea7:pyproject.toml 2>/dev/null | head -120 || true


echo '=== whiteducksoftware/flock 2025-08 technical_debt ==='
git -C '../treatment-repos/whiteducksoftware_flock' rev-parse --is-inside-work-tree
git -C '../treatment-repos/whiteducksoftware_flock' ls-tree -r --name-only 88b363080e95e8bdd87e32924216febb6cb5e4c7 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/whiteducksoftware_flock' ls-tree -r --name-only 88b363080e95e8bdd87e32924216febb6cb5e4c7 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/whiteducksoftware_flock' show 88b363080e95e8bdd87e32924216febb6cb5e4c7:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/whiteducksoftware_flock' show 88b363080e95e8bdd87e32924216febb6cb5e4c7:pyproject.toml 2>/dev/null | head -120 || true


echo '=== lancedb/lancedb 2025-03 cognitive_complexity ==='
git -C '../control-repos/lancedb_lancedb' rev-parse --is-inside-work-tree
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only e59f9382a0de2f70b931373b29a11a27824bf639 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/lancedb_lancedb' ls-tree -r --name-only e59f9382a0de2f70b931373b29a11a27824bf639 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/lancedb_lancedb' show e59f9382a0de2f70b931373b29a11a27824bf639:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/lancedb_lancedb' show e59f9382a0de2f70b931373b29a11a27824bf639:pyproject.toml 2>/dev/null | head -120 || true


echo '=== whiteducksoftware/flock 2025-05 technical_debt ==='
git -C '../treatment-repos/whiteducksoftware_flock' rev-parse --is-inside-work-tree
git -C '../treatment-repos/whiteducksoftware_flock' ls-tree -r --name-only c60e12a13b66d7f9b7c92f42c2681e331c8ed31d | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/whiteducksoftware_flock' ls-tree -r --name-only c60e12a13b66d7f9b7c92f42c2681e331c8ed31d | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/whiteducksoftware_flock' show c60e12a13b66d7f9b7c92f42c2681e331c8ed31d:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/whiteducksoftware_flock' show c60e12a13b66d7f9b7c92f42c2681e331c8ed31d:pyproject.toml 2>/dev/null | head -120 || true


echo '=== whiteducksoftware/flock 2025-06 technical_debt ==='
git -C '../treatment-repos/whiteducksoftware_flock' rev-parse --is-inside-work-tree
git -C '../treatment-repos/whiteducksoftware_flock' ls-tree -r --name-only db5e65e61bdb943cae439f796be085c5a8218a3c | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/whiteducksoftware_flock' ls-tree -r --name-only db5e65e61bdb943cae439f796be085c5a8218a3c | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/whiteducksoftware_flock' show db5e65e61bdb943cae439f796be085c5a8218a3c:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/whiteducksoftware_flock' show db5e65e61bdb943cae439f796be085c5a8218a3c:pyproject.toml 2>/dev/null | head -120 || true


echo '=== ysj9909/SHViT 2024-04 static_analysis_warnings ==='
git -C '../control-repos/ysj9909_SHViT' rev-parse --is-inside-work-tree
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only fee7ce4258e81baf9e929e90f26168d632d186a7 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only fee7ce4258e81baf9e929e90f26168d632d186a7 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/ysj9909_SHViT' show fee7ce4258e81baf9e929e90f26168d632d186a7:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/ysj9909_SHViT' show fee7ce4258e81baf9e929e90f26168d632d186a7:pyproject.toml 2>/dev/null | head -120 || true


echo '=== ysj9909/SHViT 2024-06 static_analysis_warnings ==='
git -C '../control-repos/ysj9909_SHViT' rev-parse --is-inside-work-tree
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only 6a729ccf18e0b941714b529638bd3d9bacebcef0 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only 6a729ccf18e0b941714b529638bd3d9bacebcef0 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/ysj9909_SHViT' show 6a729ccf18e0b941714b529638bd3d9bacebcef0:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/ysj9909_SHViT' show 6a729ccf18e0b941714b529638bd3d9bacebcef0:pyproject.toml 2>/dev/null | head -120 || true


echo '=== ysj9909/SHViT 2024-05 static_analysis_warnings ==='
git -C '../control-repos/ysj9909_SHViT' rev-parse --is-inside-work-tree
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only 20819cb8f624e183b1fa2ce941ed18ab8037b07d | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only 20819cb8f624e183b1fa2ce941ed18ab8037b07d | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/ysj9909_SHViT' show 20819cb8f624e183b1fa2ce941ed18ab8037b07d:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/ysj9909_SHViT' show 20819cb8f624e183b1fa2ce941ed18ab8037b07d:pyproject.toml 2>/dev/null | head -120 || true


echo '=== ysj9909/SHViT 2024-06 code_smells ==='
git -C '../control-repos/ysj9909_SHViT' rev-parse --is-inside-work-tree
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only 6a729ccf18e0b941714b529638bd3d9bacebcef0 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only 6a729ccf18e0b941714b529638bd3d9bacebcef0 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/ysj9909_SHViT' show 6a729ccf18e0b941714b529638bd3d9bacebcef0:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/ysj9909_SHViT' show 6a729ccf18e0b941714b529638bd3d9bacebcef0:pyproject.toml 2>/dev/null | head -120 || true


echo '=== ysj9909/SHViT 2024-04 code_smells ==='
git -C '../control-repos/ysj9909_SHViT' rev-parse --is-inside-work-tree
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only fee7ce4258e81baf9e929e90f26168d632d186a7 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only fee7ce4258e81baf9e929e90f26168d632d186a7 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/ysj9909_SHViT' show fee7ce4258e81baf9e929e90f26168d632d186a7:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/ysj9909_SHViT' show fee7ce4258e81baf9e929e90f26168d632d186a7:pyproject.toml 2>/dev/null | head -120 || true


echo '=== ysj9909/SHViT 2024-05 code_smells ==='
git -C '../control-repos/ysj9909_SHViT' rev-parse --is-inside-work-tree
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only 20819cb8f624e183b1fa2ce941ed18ab8037b07d | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/ysj9909_SHViT' ls-tree -r --name-only 20819cb8f624e183b1fa2ce941ed18ab8037b07d | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/ysj9909_SHViT' show 20819cb8f624e183b1fa2ce941ed18ab8037b07d:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/ysj9909_SHViT' show 20819cb8f624e183b1fa2ce941ed18ab8037b07d:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zhipeixu/FakeShield 2025-03 static_analysis_warnings ==='
git -C '../control-repos/zhipeixu_FakeShield' rev-parse --is-inside-work-tree
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 7bd43c8badef7341807e85e55a8b216dac6c2424 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 7bd43c8badef7341807e85e55a8b216dac6c2424 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/zhipeixu_FakeShield' show 7bd43c8badef7341807e85e55a8b216dac6c2424:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/zhipeixu_FakeShield' show 7bd43c8badef7341807e85e55a8b216dac6c2424:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zhipeixu/FakeShield 2025-06 static_analysis_warnings ==='
git -C '../control-repos/zhipeixu_FakeShield' rev-parse --is-inside-work-tree
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 346cb6c74c9a426c1c00d98b13e5f417161a94c1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 346cb6c74c9a426c1c00d98b13e5f417161a94c1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/zhipeixu_FakeShield' show 346cb6c74c9a426c1c00d98b13e5f417161a94c1:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/zhipeixu_FakeShield' show 346cb6c74c9a426c1c00d98b13e5f417161a94c1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zhipeixu/FakeShield 2025-02 static_analysis_warnings ==='
git -C '../control-repos/zhipeixu_FakeShield' rev-parse --is-inside-work-tree
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only b807b92ac958678bb278e741864ba4b821fb73c1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only b807b92ac958678bb278e741864ba4b821fb73c1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/zhipeixu_FakeShield' show b807b92ac958678bb278e741864ba4b821fb73c1:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/zhipeixu_FakeShield' show b807b92ac958678bb278e741864ba4b821fb73c1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zhipeixu/FakeShield 2025-05 static_analysis_warnings ==='
git -C '../control-repos/zhipeixu_FakeShield' rev-parse --is-inside-work-tree
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only c34dab9b8df3dc77d2632344eb0d0af387d0658f | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only c34dab9b8df3dc77d2632344eb0d0af387d0658f | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/zhipeixu_FakeShield' show c34dab9b8df3dc77d2632344eb0d0af387d0658f:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/zhipeixu_FakeShield' show c34dab9b8df3dc77d2632344eb0d0af387d0658f:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zhipeixu/FakeShield 2025-04 static_analysis_warnings ==='
git -C '../control-repos/zhipeixu_FakeShield' rev-parse --is-inside-work-tree
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 2910fb826ea20e11c2c2553c36984630216c0bab | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 2910fb826ea20e11c2c2553c36984630216c0bab | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/zhipeixu_FakeShield' show 2910fb826ea20e11c2c2553c36984630216c0bab:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/zhipeixu_FakeShield' show 2910fb826ea20e11c2c2553c36984630216c0bab:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zhipeixu/FakeShield 2025-02 code_smells ==='
git -C '../control-repos/zhipeixu_FakeShield' rev-parse --is-inside-work-tree
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only b807b92ac958678bb278e741864ba4b821fb73c1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only b807b92ac958678bb278e741864ba4b821fb73c1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/zhipeixu_FakeShield' show b807b92ac958678bb278e741864ba4b821fb73c1:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/zhipeixu_FakeShield' show b807b92ac958678bb278e741864ba4b821fb73c1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zhipeixu/FakeShield 2025-03 code_smells ==='
git -C '../control-repos/zhipeixu_FakeShield' rev-parse --is-inside-work-tree
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 7bd43c8badef7341807e85e55a8b216dac6c2424 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 7bd43c8badef7341807e85e55a8b216dac6c2424 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/zhipeixu_FakeShield' show 7bd43c8badef7341807e85e55a8b216dac6c2424:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/zhipeixu_FakeShield' show 7bd43c8badef7341807e85e55a8b216dac6c2424:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zhipeixu/FakeShield 2025-04 code_smells ==='
git -C '../control-repos/zhipeixu_FakeShield' rev-parse --is-inside-work-tree
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 2910fb826ea20e11c2c2553c36984630216c0bab | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 2910fb826ea20e11c2c2553c36984630216c0bab | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/zhipeixu_FakeShield' show 2910fb826ea20e11c2c2553c36984630216c0bab:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/zhipeixu_FakeShield' show 2910fb826ea20e11c2c2553c36984630216c0bab:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zhipeixu/FakeShield 2025-06 code_smells ==='
git -C '../control-repos/zhipeixu_FakeShield' rev-parse --is-inside-work-tree
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 346cb6c74c9a426c1c00d98b13e5f417161a94c1 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only 346cb6c74c9a426c1c00d98b13e5f417161a94c1 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/zhipeixu_FakeShield' show 346cb6c74c9a426c1c00d98b13e5f417161a94c1:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/zhipeixu_FakeShield' show 346cb6c74c9a426c1c00d98b13e5f417161a94c1:pyproject.toml 2>/dev/null | head -120 || true


echo '=== zhipeixu/FakeShield 2025-05 code_smells ==='
git -C '../control-repos/zhipeixu_FakeShield' rev-parse --is-inside-work-tree
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only c34dab9b8df3dc77d2632344eb0d0af387d0658f | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/zhipeixu_FakeShield' ls-tree -r --name-only c34dab9b8df3dc77d2632344eb0d0af387d0658f | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/zhipeixu_FakeShield' show c34dab9b8df3dc77d2632344eb0d0af387d0658f:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/zhipeixu_FakeShield' show c34dab9b8df3dc77d2632344eb0d0af387d0658f:pyproject.toml 2>/dev/null | head -120 || true


echo '=== getsentry/sentry 2025-07 bugs ==='
git -C '../treatment-repos/getsentry_sentry' rev-parse --is-inside-work-tree
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only 71c2f5f3925610f3aa1871ace1c20f48eeff3db8 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only 71c2f5f3925610f3aa1871ace1c20f48eeff3db8 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/getsentry_sentry' show 71c2f5f3925610f3aa1871ace1c20f48eeff3db8:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/getsentry_sentry' show 71c2f5f3925610f3aa1871ace1c20f48eeff3db8:pyproject.toml 2>/dev/null | head -120 || true


echo '=== getsentry/sentry 2025-08 bugs ==='
git -C '../treatment-repos/getsentry_sentry' rev-parse --is-inside-work-tree
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only b9dc9712a91c4dbf3cb1550254113c1599388e57 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only b9dc9712a91c4dbf3cb1550254113c1599388e57 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/getsentry_sentry' show b9dc9712a91c4dbf3cb1550254113c1599388e57:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/getsentry_sentry' show b9dc9712a91c4dbf3cb1550254113c1599388e57:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PostHog/posthog 2025-07 technical_debt ==='
git -C '../treatment-repos/PostHog_posthog' rev-parse --is-inside-work-tree
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/PostHog_posthog' ls-tree -r --name-only 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/PostHog_posthog' show 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/PostHog_posthog' show 8e13bf3cbfe9684eb907f7ddf706aa9fae2099e0:pyproject.toml 2>/dev/null | head -120 || true


echo '=== getsentry/sentry 2025-06 bugs ==='
git -C '../treatment-repos/getsentry_sentry' rev-parse --is-inside-work-tree
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only 4f2be477198bf2814c6d6cd4b80ba19cbe386908 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only 4f2be477198bf2814c6d6cd4b80ba19cbe386908 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/getsentry_sentry' show 4f2be477198bf2814c6d6cd4b80ba19cbe386908:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/getsentry_sentry' show 4f2be477198bf2814c6d6cd4b80ba19cbe386908:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2024-11 static_analysis_warnings ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 51ad26394a2b99ed8dfab0bd1538abfca73db233 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 51ad26394a2b99ed8dfab0bd1538abfca73db233 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show 51ad26394a2b99ed8dfab0bd1538abfca73db233:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show 51ad26394a2b99ed8dfab0bd1538abfca73db233:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2024-10 static_analysis_warnings ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 46280de29975a61a5d4cd09f36c806a2fb7db769 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 46280de29975a61a5d4cd09f36c806a2fb7db769 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show 46280de29975a61a5d4cd09f36c806a2fb7db769:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show 46280de29975a61a5d4cd09f36c806a2fb7db769:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2025-05 static_analysis_warnings ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 7516af8388fd968e6b7abbfb0df7d51d658142d2 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 7516af8388fd968e6b7abbfb0df7d51d658142d2 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show 7516af8388fd968e6b7abbfb0df7d51d658142d2:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show 7516af8388fd968e6b7abbfb0df7d51d658142d2:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2025-04 static_analysis_warnings ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only e07b38ed8d6e89f0887aa5ec6712934467742b36 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only e07b38ed8d6e89f0887aa5ec6712934467742b36 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show e07b38ed8d6e89f0887aa5ec6712934467742b36:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show e07b38ed8d6e89f0887aa5ec6712934467742b36:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2025-06 static_analysis_warnings ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only cb3628112394669d5a93a5804f4d6e23cf161eba | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only cb3628112394669d5a93a5804f4d6e23cf161eba | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show cb3628112394669d5a93a5804f4d6e23cf161eba:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show cb3628112394669d5a93a5804f4d6e23cf161eba:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2025-07 static_analysis_warnings ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only a7737126dae693f755013f0fcd11df7867274df6 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only a7737126dae693f755013f0fcd11df7867274df6 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show a7737126dae693f755013f0fcd11df7867274df6:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show a7737126dae693f755013f0fcd11df7867274df6:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2025-02 static_analysis_warnings ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 4c2b99a126d0f7ad8d13f5c55e098b07c3f51045 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 4c2b99a126d0f7ad8d13f5c55e098b07c3f51045 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show 4c2b99a126d0f7ad8d13f5c55e098b07c3f51045:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show 4c2b99a126d0f7ad8d13f5c55e098b07c3f51045:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2024-08 static_analysis_warnings ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 03281501945c2ae93ad35c5a618178d65bb2d0d8 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 03281501945c2ae93ad35c5a618178d65bb2d0d8 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show 03281501945c2ae93ad35c5a618178d65bb2d0d8:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show 03281501945c2ae93ad35c5a618178d65bb2d0d8:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2024-07 static_analysis_warnings ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 8840d02caab67fec49efe08a7912d1f39949a100 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 8840d02caab67fec49efe08a7912d1f39949a100 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show 8840d02caab67fec49efe08a7912d1f39949a100:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show 8840d02caab67fec49efe08a7912d1f39949a100:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2024-05 static_analysis_warnings ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 59566a650f2624f2fc214bd9d8b3c5e7d825da57 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 59566a650f2624f2fc214bd9d8b3c5e7d825da57 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show 59566a650f2624f2fc214bd9d8b3c5e7d825da57:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show 59566a650f2624f2fc214bd9d8b3c5e7d825da57:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2024-01 static_analysis_warnings ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 47ae5be927e7c079ca0b9a6b01b811bf9ffcf9bd | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 47ae5be927e7c079ca0b9a6b01b811bf9ffcf9bd | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show 47ae5be927e7c079ca0b9a6b01b811bf9ffcf9bd:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show 47ae5be927e7c079ca0b9a6b01b811bf9ffcf9bd:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2024-03 static_analysis_warnings ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only fc623e81f9e7476938a04e191b471aa90dc11d76 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only fc623e81f9e7476938a04e191b471aa90dc11d76 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show fc623e81f9e7476938a04e191b471aa90dc11d76:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show fc623e81f9e7476938a04e191b471aa90dc11d76:pyproject.toml 2>/dev/null | head -120 || true


echo '=== getsentry/sentry 2024-12 bugs ==='
git -C '../treatment-repos/getsentry_sentry' rev-parse --is-inside-work-tree
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only 707f353d2d1933fbf951478c414838f9e5956b38 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only 707f353d2d1933fbf951478c414838f9e5956b38 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/getsentry_sentry' show 707f353d2d1933fbf951478c414838f9e5956b38:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/getsentry_sentry' show 707f353d2d1933fbf951478c414838f9e5956b38:pyproject.toml 2>/dev/null | head -120 || true


echo '=== getsentry/sentry 2024-11 bugs ==='
git -C '../treatment-repos/getsentry_sentry' rev-parse --is-inside-work-tree
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only 8e45680a887ec96c50c1f43fffe1ac8f2b6c54aa | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only 8e45680a887ec96c50c1f43fffe1ac8f2b6c54aa | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/getsentry_sentry' show 8e45680a887ec96c50c1f43fffe1ac8f2b6c54aa:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/getsentry_sentry' show 8e45680a887ec96c50c1f43fffe1ac8f2b6c54aa:pyproject.toml 2>/dev/null | head -120 || true


echo '=== getsentry/sentry 2025-01 bugs ==='
git -C '../treatment-repos/getsentry_sentry' rev-parse --is-inside-work-tree
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only d210118fce94310ef5858d51efe16ee26c995a48 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only d210118fce94310ef5858d51efe16ee26c995a48 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/getsentry_sentry' show d210118fce94310ef5858d51efe16ee26c995a48:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/getsentry_sentry' show d210118fce94310ef5858d51efe16ee26c995a48:pyproject.toml 2>/dev/null | head -120 || true


echo '=== getsentry/sentry 2025-02 bugs ==='
git -C '../treatment-repos/getsentry_sentry' rev-parse --is-inside-work-tree
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only c4502d06cff34abeb8f58810743fb907ee914348 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only c4502d06cff34abeb8f58810743fb907ee914348 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/getsentry_sentry' show c4502d06cff34abeb8f58810743fb907ee914348:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/getsentry_sentry' show c4502d06cff34abeb8f58810743fb907ee914348:pyproject.toml 2>/dev/null | head -120 || true


echo '=== getsentry/sentry 2024-10 bugs ==='
git -C '../treatment-repos/getsentry_sentry' rev-parse --is-inside-work-tree
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only ad46b361e2e960136b68f1647b936af1b3f6752a | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only ad46b361e2e960136b68f1647b936af1b3f6752a | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/getsentry_sentry' show ad46b361e2e960136b68f1647b936af1b3f6752a:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/getsentry_sentry' show ad46b361e2e960136b68f1647b936af1b3f6752a:pyproject.toml 2>/dev/null | head -120 || true


echo '=== getsentry/sentry 2024-09 bugs ==='
git -C '../treatment-repos/getsentry_sentry' rev-parse --is-inside-work-tree
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only 6c6024b9d8999b88166c60580a677d809252fc04 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/getsentry_sentry' ls-tree -r --name-only 6c6024b9d8999b88166c60580a677d809252fc04 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/getsentry_sentry' show 6c6024b9d8999b88166c60580a677d809252fc04:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/getsentry_sentry' show 6c6024b9d8999b88166c60580a677d809252fc04:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-08 static_analysis_warnings ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 0150699ff9adda89142bf65e2600619d61f6d55a | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 0150699ff9adda89142bf65e2600619d61f6d55a | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show 0150699ff9adda89142bf65e2600619d61f6d55a:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show 0150699ff9adda89142bf65e2600619d61f6d55a:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-07 static_analysis_warnings ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 4f4b01a142d5224279c4d0fcd6b944fcc80b343b | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 4f4b01a142d5224279c4d0fcd6b944fcc80b343b | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show 4f4b01a142d5224279c4d0fcd6b944fcc80b343b:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show 4f4b01a142d5224279c4d0fcd6b944fcc80b343b:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-06 static_analysis_warnings ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only f43af48a983a734ca863a04362b99176d506bcb8 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only f43af48a983a734ca863a04362b99176d506bcb8 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show f43af48a983a734ca863a04362b99176d506bcb8:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show f43af48a983a734ca863a04362b99176d506bcb8:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-05 static_analysis_warnings ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 06db0834814629bbac4bea9188101898cc4b0a91 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 06db0834814629bbac4bea9188101898cc4b0a91 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show 06db0834814629bbac4bea9188101898cc4b0a91:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show 06db0834814629bbac4bea9188101898cc4b0a91:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-08 code_smells ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 0150699ff9adda89142bf65e2600619d61f6d55a | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 0150699ff9adda89142bf65e2600619d61f6d55a | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show 0150699ff9adda89142bf65e2600619d61f6d55a:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show 0150699ff9adda89142bf65e2600619d61f6d55a:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-07 code_smells ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 4f4b01a142d5224279c4d0fcd6b944fcc80b343b | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 4f4b01a142d5224279c4d0fcd6b944fcc80b343b | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show 4f4b01a142d5224279c4d0fcd6b944fcc80b343b:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show 4f4b01a142d5224279c4d0fcd6b944fcc80b343b:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-06 code_smells ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only f43af48a983a734ca863a04362b99176d506bcb8 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only f43af48a983a734ca863a04362b99176d506bcb8 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show f43af48a983a734ca863a04362b99176d506bcb8:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show f43af48a983a734ca863a04362b99176d506bcb8:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-05 code_smells ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 06db0834814629bbac4bea9188101898cc4b0a91 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 06db0834814629bbac4bea9188101898cc4b0a91 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show 06db0834814629bbac4bea9188101898cc4b0a91:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show 06db0834814629bbac4bea9188101898cc4b0a91:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2024-11 bugs ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 51ad26394a2b99ed8dfab0bd1538abfca73db233 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 51ad26394a2b99ed8dfab0bd1538abfca73db233 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show 51ad26394a2b99ed8dfab0bd1538abfca73db233:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show 51ad26394a2b99ed8dfab0bd1538abfca73db233:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2025-05 bugs ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 7516af8388fd968e6b7abbfb0df7d51d658142d2 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 7516af8388fd968e6b7abbfb0df7d51d658142d2 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show 7516af8388fd968e6b7abbfb0df7d51d658142d2:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show 7516af8388fd968e6b7abbfb0df7d51d658142d2:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2025-02 bugs ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 4c2b99a126d0f7ad8d13f5c55e098b07c3f51045 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 4c2b99a126d0f7ad8d13f5c55e098b07c3f51045 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show 4c2b99a126d0f7ad8d13f5c55e098b07c3f51045:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show 4c2b99a126d0f7ad8d13f5c55e098b07c3f51045:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2025-04 bugs ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only e07b38ed8d6e89f0887aa5ec6712934467742b36 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only e07b38ed8d6e89f0887aa5ec6712934467742b36 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show e07b38ed8d6e89f0887aa5ec6712934467742b36:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show e07b38ed8d6e89f0887aa5ec6712934467742b36:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2025-06 bugs ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only cb3628112394669d5a93a5804f4d6e23cf161eba | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only cb3628112394669d5a93a5804f4d6e23cf161eba | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show cb3628112394669d5a93a5804f4d6e23cf161eba:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show cb3628112394669d5a93a5804f4d6e23cf161eba:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2024-10 bugs ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 46280de29975a61a5d4cd09f36c806a2fb7db769 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 46280de29975a61a5d4cd09f36c806a2fb7db769 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show 46280de29975a61a5d4cd09f36c806a2fb7db769:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show 46280de29975a61a5d4cd09f36c806a2fb7db769:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2025-07 bugs ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only a7737126dae693f755013f0fcd11df7867274df6 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only a7737126dae693f755013f0fcd11df7867274df6 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show a7737126dae693f755013f0fcd11df7867274df6:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show a7737126dae693f755013f0fcd11df7867274df6:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2024-05 bugs ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 59566a650f2624f2fc214bd9d8b3c5e7d825da57 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 59566a650f2624f2fc214bd9d8b3c5e7d825da57 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show 59566a650f2624f2fc214bd9d8b3c5e7d825da57:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show 59566a650f2624f2fc214bd9d8b3c5e7d825da57:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2024-08 bugs ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 03281501945c2ae93ad35c5a618178d65bb2d0d8 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 03281501945c2ae93ad35c5a618178d65bb2d0d8 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show 03281501945c2ae93ad35c5a618178d65bb2d0d8:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show 03281501945c2ae93ad35c5a618178d65bb2d0d8:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2024-07 bugs ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 8840d02caab67fec49efe08a7912d1f39949a100 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 8840d02caab67fec49efe08a7912d1f39949a100 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show 8840d02caab67fec49efe08a7912d1f39949a100:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show 8840d02caab67fec49efe08a7912d1f39949a100:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2024-03 bugs ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only fc623e81f9e7476938a04e191b471aa90dc11d76 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only fc623e81f9e7476938a04e191b471aa90dc11d76 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show fc623e81f9e7476938a04e191b471aa90dc11d76:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show fc623e81f9e7476938a04e191b471aa90dc11d76:pyproject.toml 2>/dev/null | head -120 || true


echo '=== jacebrowning/datafiles 2024-01 bugs ==='
git -C '../control-repos/jacebrowning_datafiles' rev-parse --is-inside-work-tree
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 47ae5be927e7c079ca0b9a6b01b811bf9ffcf9bd | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/jacebrowning_datafiles' ls-tree -r --name-only 47ae5be927e7c079ca0b9a6b01b811bf9ffcf9bd | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/jacebrowning_datafiles' show 47ae5be927e7c079ca0b9a6b01b811bf9ffcf9bd:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/jacebrowning_datafiles' show 47ae5be927e7c079ca0b9a6b01b811bf9ffcf9bd:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-03 code_smells ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only d5329df09ed618392f858c17160e1d7833a2588c | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only d5329df09ed618392f858c17160e1d7833a2588c | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show d5329df09ed618392f858c17160e1d7833a2588c:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show d5329df09ed618392f858c17160e1d7833a2588c:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-01 code_smells ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only d7391b2a18820e80af59095204f668f1758e2278 | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only d7391b2a18820e80af59095204f668f1758e2278 | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show d7391b2a18820e80af59095204f668f1758e2278:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show d7391b2a18820e80af59095204f668f1758e2278:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2025-02 code_smells ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only f4f4105451484b80b4fb3f71dc41ff395c188cce | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only f4f4105451484b80b4fb3f71dc41ff395c188cce | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show f4f4105451484b80b4fb3f71dc41ff395c188cce:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show f4f4105451484b80b4fb3f71dc41ff395c188cce:pyproject.toml 2>/dev/null | head -120 || true


echo '=== PennyLaneAI/catalyst 2024-12 code_smells ==='
git -C '../control-repos/PennyLaneAI_catalyst' rev-parse --is-inside-work-tree
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 4ab437d35491088597bb6f2e4261bab3c3cedc2b | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../control-repos/PennyLaneAI_catalyst' ls-tree -r --name-only 4ab437d35491088597bb6f2e4261bab3c3cedc2b | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../control-repos/PennyLaneAI_catalyst' show 4ab437d35491088597bb6f2e4261bab3c3cedc2b:sonar-project.properties 2>/dev/null || true
git -C '../control-repos/PennyLaneAI_catalyst' show 4ab437d35491088597bb6f2e4261bab3c3cedc2b:pyproject.toml 2>/dev/null | head -120 || true


echo '=== cgevans/qslib 2025-05 static_analysis_warnings ==='
git -C '../treatment-repos/cgevans_qslib' rev-parse --is-inside-work-tree
git -C '../treatment-repos/cgevans_qslib' ls-tree -r --name-only d02b38180d3a4f06775d13e613b0f382447d7c6b | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/cgevans_qslib' ls-tree -r --name-only d02b38180d3a4f06775d13e613b0f382447d7c6b | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/cgevans_qslib' show d02b38180d3a4f06775d13e613b0f382447d7c6b:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/cgevans_qslib' show d02b38180d3a4f06775d13e613b0f382447d7c6b:pyproject.toml 2>/dev/null | head -120 || true


echo '=== cgevans/qslib 2025-05 code_smells ==='
git -C '../treatment-repos/cgevans_qslib' rev-parse --is-inside-work-tree
git -C '../treatment-repos/cgevans_qslib' ls-tree -r --name-only d02b38180d3a4f06775d13e613b0f382447d7c6b | awk -F/ '{print $1}' | sort | uniq -c | sort -nr | head -30
git -C '../treatment-repos/cgevans_qslib' ls-tree -r --name-only d02b38180d3a4f06775d13e613b0f382447d7c6b | grep -E '\.(py|ipynb|js|ts|tsx|jsx)$' | wc -l
git -C '../treatment-repos/cgevans_qslib' show d02b38180d3a4f06775d13e613b0f382447d7c6b:sonar-project.properties 2>/dev/null || true
git -C '../treatment-repos/cgevans_qslib' show d02b38180d3a4f06775d13e613b0f382447d7c6b:pyproject.toml 2>/dev/null | head -120 || true

