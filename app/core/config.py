from pydantic_settings import BaseSettings
import base64
import tempfile
import os
from typing import Optional

class Settings(BaseSettings):
    DATABASE_URL: str

    # Configurações NFSe Recife
    # Opção 1: Caminhos para arquivos locais (desenvolvimento)
    NFSE_CERT_PATH: Optional[str] = None
    NFSE_KEY_PATH: Optional[str] = None

    # Opção 2: Conteúdo base64 (produção/Easypanel)
    NFSE_CERT_BASE64: Optional[str] = None
    NFSE_KEY_BASE64: Optional[str] = None

    NFSE_CNPJ: str = "08857492000148"
    NFSE_INSCRICAO_MUNICIPAL: str = "3694208"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def get_cert_paths(self) -> tuple[str, str]:
        """
        Retorna os caminhos dos certificados.
        Se fornecido via base64, cria arquivos temporários.
        """
        # Se já tiver paths definidos, usa eles
        if self.NFSE_CERT_PATH and self.NFSE_KEY_PATH:
            return self.NFSE_CERT_PATH, self.NFSE_KEY_PATH

        # Se tiver base64, decodifica e cria arquivos temporários
        if self.NFSE_CERT_BASE64 and self.NFSE_KEY_BASE64:
            # Decodifica os certificados
            cert_content = base64.b64decode(self.NFSE_CERT_BASE64)
            key_content = base64.b64decode(self.NFSE_KEY_BASE64)

            # Cria arquivos temporários
            cert_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.crt')
            key_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.key')

            cert_file.write(cert_content)
            key_file.write(key_content)

            cert_file.close()
            key_file.close()

            return cert_file.name, key_file.name

        raise ValueError(
            "Certificados NFSe não configurados. "
            "Configure NFSE_CERT_PATH/NFSE_KEY_PATH ou NFSE_CERT_BASE64/NFSE_KEY_BASE64"
        )

settings = Settings()
