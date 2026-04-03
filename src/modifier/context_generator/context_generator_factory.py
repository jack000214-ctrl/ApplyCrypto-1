from config.config_manager import Configuration
from modifier.code_generator.base_code_generator import BaseCodeGenerator
from modifier.context_generator.base_context_generator import BaseContextGenerator

class ContextGeneratorFactory:
    """
    Factory for creating ContextGenerator instances.
    """

    @staticmethod
    def create(
        config: Configuration, code_generator: BaseCodeGenerator
    ) -> BaseContextGenerator:
        """
        Creates a ContextGenerator instance.

        Args:
            config: Configuration object.
            code_generator: CodeGenerator instance.

        Returns:
            BaseContextGenerator: An instance of ContextGenerator.

        ** Important **
        향후 개발 시 (아래 AnyframeSarangon 예시와 같이), 반드시 프레임워크 타입 기반의 config key를 사용해주세요

        """

        if config.framework_type == "Anyframe":
            from modifier.context_generator.anyframe_context_generator import AnyframeContextGenerator

            return AnyframeContextGenerator(config, code_generator)

        elif config.framework_type == "AnyframeRps":
            from modifier.context_generator.anyframe_rps_context_generator import AnyframeRpsContextGenerator

            return AnyframeRpsContextGenerator(config, code_generator)

        elif config.framework_type == "AnyframeRps2":
            from modifier.context_generator.anyframe_rps2_context_generator import AnyframeRps2ContextGenerator

            return AnyframeRps2ContextGenerator(config, code_generator)

        elif config.sql_wrapping_type == "mybatis" or config.sql_wrapping_type == "mybatis_digital_channel":
            if config.modification_type == "TypeHandler":
                from modifier.context_generator.typehandler_context_generator import TypehandlerContextGenerator

                return TypehandlerContextGenerator(config, code_generator)
            else:
                from modifier.context_generator.mybatis_context_generator import MybatisContextGenerator

                return MybatisContextGenerator(config, code_generator)

        elif config.sql_wrapping_type == "mybatis_pointcore":
            from modifier.context_generator.mybatis_context_generator import MybatisContextGenerator

            return MybatisContextGenerator(config, code_generator)

        elif config.sql_wrapping_type == "mybatis_wm":
            from modifier.context_generator.mybatis_wm_context_generator import MybatisWmContextGenerator

            return MybatisWmContextGenerator(config, code_generator)

        elif config.sql_wrapping_type == "mybatis_ccs":
            from modifier.context_generator.mybatis_ccs_context_generator import MybatisCCSContextGenerator

            return MybatisCCSContextGenerator(config, code_generator)

        elif config.sql_wrapping_type == "ccs_batch":
            from modifier.context_generator.ccs_batch_context_generator import CCSBatchContextGenerator

            return CCSBatchContextGenerator(config, code_generator)

        elif config.sql_wrapping_type == "bnk_batch":
            from modifier.context_generator.bnk_batch_context_generator import BNKBatchContextGenerator

            return BNKBatchContextGenerator(config, code_generator)

        elif config.sql_wrapping_type == "mybatis_revolution_bat":
            from modifier.context_generator.mybatis_revolution_bat_context_generator import MybatisRevolutionBatContextGenerator

            return MybatisRevolutionBatContextGenerator(config, code_generator)

        elif config.sql_wrapping_type == "mybatis_drt":
            from modifier.context_generator.mybatis_drt_context_generator import MybatisDrtContextGenerator

            return MybatisDrtContextGenerator(config, code_generator)

        elif config.sql_wrapping_type == "jdbc_banka":
            from modifier.context_generator.anyframe_banka_context_generator import (
                AnyframeBankaContextGenerator,
            )

            return AnyframeBankaContextGenerator(config, code_generator)

        elif config.sql_wrapping_type == "jdbc_sarangon":
            from modifier.context_generator.anyframe_sarangon_context_generator import (
                AnyframeSarangonContextGenerator,
            )

            return AnyframeSarangonContextGenerator(config, code_generator)

        else:
            from modifier.context_generator.per_layer_context_generator import PerLayerContextGenerator

            return PerLayerContextGenerator(config, code_generator)