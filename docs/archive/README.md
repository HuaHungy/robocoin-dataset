# 文档归档说明

本目录存放已归档的历史文档，按以下分类组织：

## 📂 目录结构

### 1. `daily_summaries/` - 日常工作总结
存放按日期记录的工作总结、进度报告和完成记录
- `SESSION_*` - 工作会话总结
- `WORK_*` - 工作完成记录
- `TODAY_*` - 当日进度总结
- `FINAL_*` - 阶段性最终总结
- `PROGRESS_*` - 进度报告

### 2. `fixes/` - 问题修复记录
存放各种bug修复、问题解决的详细记录
- 配置修复（`CONFIG_FIXES_*`）
- 内存泄漏修复（`MEMORY_LEAK_*`）
- 数据库修复（`DATABASE_*`）
- 其他各类修复记录

### 3. `old_analysis/` - 历史分析文档
存放早期的数据分析、问题分析文档
- 数据格式分析
- 性能分析
- 架构分析
- 重构计划

### 4. `config_work/` - 配置相关工作
存放配置文件开发、修复、验证的历史记录
- 配置修复
- 配置总结
- 配置分析

### 5. `validation_work/` - 验证相关工作
存放数据验证、配置验证相关的历史文档
- 验证器开发记录
- 验证结果
- 预验证增强
- 测试模式相关

### 6. `device_specific/` - 设备专属文档
按设备品牌分类存放各设备的历史开发文档
- `agilex/` - Agilex机器人相关
- `galaxea/` - Galaxea机器人相关
- `leju/` - 乐聚机器人相关
- `mmk2/` - MMK2机器人相关
- `realman/` - 睿尔曼机器人相关
- `ruantong/` - 软通机器人相关
- `yinhe/` - 银河机器人相关
- `zhipingfang/` - 至平方机器人相关

### 7. `guides/` - 使用指南
存放各种操作指南和使用说明

### 8. `features/` - 特性开发记录
存放各种功能特性的开发记录
- 容错机制
- 检查点恢复
- 视频压缩
- 自动重编码

### 9. `converter_work/` - 转换器开发工作
存放转换器相关的历史开发文档

### 10. `database_work/` - 数据库相关工作
存放数据库相关的历史开发文档

## 📌 核心文档（docs根目录）

当前在`docs/`根目录保留的核心文档：
- `PROJECT_DOCUMENTATION_INDEX.md` - 项目文档索引（入口）
- `PROJECT_SUMMARY_FINAL.md` - 项目总结报告
- `ALL_PITFALLS_AND_ROBOT_DATA_CHAOS.md` - 项目坑点与机器人数据混乱分析
- `PERSONAL_PROJECT_SUMMARY.md` - 个人项目总结（简历用）
- `PROJECT_ARCHITECTURE_DIAGRAM.md` - 项目架构图
- `README.md` - 项目文档说明
- `AUTO_REENCODE_INTEGRATION.md` - 自动重编码集成文档
- `COMPREHENSIVE_TASK_SUMMARY.md` - 综合任务总结
- `CONFIG_FIELD_NAMING.md` - 配置字段命名规范
- `CONVERTER_DEPTH_COMPLETE_ANALYSIS.md` - 转换器深度完整分析
- `IS_TEST_MODE_ANALYSIS.md` - 测试模式分析
- `MCAP_MEMORY_ISSUE_AND_FIX.md` - MCAP内存问题与修复

## 🔍 查找历史文档

如需查找特定历史文档，建议：
1. 按日期查找：查看 `daily_summaries/`
2. 按问题类型：查看 `fixes/`
3. 按设备品牌：查看 `device_specific/`
4. 按功能模块：查看对应分类目录

## 📅 归档时间

归档日期：2025-11-06
归档原因：项目进入稳定期，整理历史文档以提高文档可读性和可维护性

