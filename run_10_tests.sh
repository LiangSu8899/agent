#!/bin/bash

# 测试脚本：运行 10 次 Agent 任务测试
# 配置: Planner: glm-4-plus | Coder: glm-4-plus

cd /home/heima/suliang/main/agent
source agent/bin/activate

TASK="帮我找到并clone higgs的github,然后给这个工程写一个http_serve.py在这个clone的工程里，最后写个这个serve脚本的readme.md文件，要中英文版的"

RESULTS_FILE="test_results_$(date +%Y%m%d_%H%M%S).txt"
SUCCESS_COUNT=0
FAIL_COUNT=0

# 初始化结果文件
echo "=== Agent OS 测试报告 ===" > $RESULTS_FILE
echo "模型配置: Planner: glm-4-plus | Coder: glm-4-plus" >> $RESULTS_FILE
echo "任务: $TASK" >> $RESULTS_FILE
echo "开始时间: $(date)" >> $RESULTS_FILE
echo "" >> $RESULTS_FILE

for i in {1..10}; do
    echo "=========================================="
    echo "开始第 $i 次测试... ($(date))"
    echo "=========================================="

    echo "--- 测试 #$i ---" >> $RESULTS_FILE
    echo "开始: $(date)" >> $RESULTS_FILE

    # 清理之前可能存在的 clone 文件夹
    rm -rf HiggsAnalysis-CombinedLimit higgs Higgs higgs-* 2>/dev/null

    # 运行任务，设置超时 5 分钟
    timeout 300 aos start "$TASK" > "test_log_$i.txt" 2>&1
    EXIT_CODE=$?

    # 检查结果
    CLONE_DIR=""
    if [ -d "HiggsAnalysis-CombinedLimit" ]; then
        CLONE_DIR="HiggsAnalysis-CombinedLimit"
    else
        CLONE_DIR=$(find . -maxdepth 1 -type d -iname "*higgs*" 2>/dev/null | head -1)
    fi

    if [ -n "$CLONE_DIR" ] && [ -d "$CLONE_DIR" ]; then
        HTTP_SERVE=$(find "$CLONE_DIR" -name "http_serve.py" 2>/dev/null | head -1)
        # 查找新创建的 readme 文件（排除原有的）
        NEW_README=$(find "$CLONE_DIR" -maxdepth 1 -iname "*readme*serve*.md" -o -iname "*http*readme*.md" 2>/dev/null | head -1)

        # 如果没找到特定的，检查是否有 http_serve 相关的 readme
        if [ -z "$NEW_README" ]; then
            NEW_README=$(find "$CLONE_DIR" -name "*.md" -newer "$CLONE_DIR/.git" 2>/dev/null | head -1)
        fi

        if [ -n "$HTTP_SERVE" ]; then
            if [ -n "$NEW_README" ]; then
                echo "测试 #$i: 成功 (完整)" | tee -a $RESULTS_FILE
                echo "  - Clone目录: $CLONE_DIR" >> $RESULTS_FILE
                echo "  - http_serve.py: $HTTP_SERVE" >> $RESULTS_FILE
                echo "  - README: $NEW_README" >> $RESULTS_FILE
                ((SUCCESS_COUNT++))
            else
                echo "测试 #$i: 部分成功 (缺少README)" | tee -a $RESULTS_FILE
                echo "  - Clone目录: $CLONE_DIR" >> $RESULTS_FILE
                echo "  - http_serve.py: $HTTP_SERVE" >> $RESULTS_FILE
                echo "  - README: 未找到新创建的" >> $RESULTS_FILE
                ((FAIL_COUNT++))
            fi
        else
            echo "测试 #$i: 失败 (缺少http_serve.py)" | tee -a $RESULTS_FILE
            echo "  - Clone目录: $CLONE_DIR" >> $RESULTS_FILE
            echo "  - http_serve.py: 未找到" >> $RESULTS_FILE
            ((FAIL_COUNT++))
        fi
    else
        echo "测试 #$i: 失败 (未找到clone目录)" | tee -a $RESULTS_FILE
        ((FAIL_COUNT++))
    fi

    echo "结束: $(date)" >> $RESULTS_FILE
    echo "退出码: $EXIT_CODE" >> $RESULTS_FILE
    echo "" >> $RESULTS_FILE

    # 清理 clone 文件夹
    rm -rf HiggsAnalysis-CombinedLimit higgs Higgs higgs-* 2>/dev/null

    echo "第 $i 次测试完成"
    echo ""

    # 短暂等待，避免 API 限流
    sleep 2
done

# 输出统计
echo "==========================================" | tee -a $RESULTS_FILE
echo "=== 测试完成 ===" | tee -a $RESULTS_FILE
echo "成功: $SUCCESS_COUNT / 10" | tee -a $RESULTS_FILE
echo "失败: $FAIL_COUNT / 10" | tee -a $RESULTS_FILE
echo "成功率: $((SUCCESS_COUNT * 100 / 10))%" | tee -a $RESULTS_FILE
echo "结束时间: $(date)" >> $RESULTS_FILE
echo "==========================================" | tee -a $RESULTS_FILE

echo ""
echo "详细结果保存在: $RESULTS_FILE"
