#!/usr/bin/env python3
"""
Script para testar o endpoint de importação de NFSe
"""
import requests
from datetime import date, timedelta

# URL da sua API (ajuste conforme necessário)
API_URL = "http://localhost:8000"

def testar_importacao_padrao():
    """Testa importação com período padrão (ontem até hoje)"""
    print("=" * 60)
    print("TESTE 1: Importação padrão (ontem até hoje)")
    print("=" * 60)

    url = f"{API_URL}/notas_servico/importar"

    print(f"\nFazendo requisição POST para: {url}")

    try:
        response = requests.post(url, timeout=60)

        print(f"\nStatus Code: {response.status_code}")
        print(f"\nResposta:")
        print("-" * 60)

        data = response.json()

        if data.get('success'):
            print("✓ SUCESSO!")
            print(f"\nPeríodo: {data['periodo']['data_inicial']} até {data['periodo']['data_final']}")
            print(f"Total encontradas: {data['total_encontradas']}")
            print(f"Total importadas: {data['total_importadas']}")
            print(f"Total atualizadas: {data['total_atualizadas']}")

            if data.get('erros'):
                print(f"\n⚠ Erros encontrados:")
                for erro in data['erros']:
                    print(f"  - NFSe {erro['nfse']}: {erro['erro']}")
        else:
            print("✗ ERRO!")
            print(f"Erro: {data.get('erro')}")
            print(f"Mensagem: {data.get('message')}")

        return response.status_code == 200 and data.get('success')

    except requests.exceptions.ConnectionError:
        print("✗ ERRO: Não foi possível conectar à API")
        print("Certifique-se de que a API está rodando!")
        return False
    except Exception as e:
        print(f"✗ ERRO: {e}")
        return False


def testar_importacao_periodo(data_inicial: str, data_final: str):
    """Testa importação com período específico"""
    print("\n" + "=" * 60)
    print(f"TESTE 2: Importação de {data_inicial} até {data_final}")
    print("=" * 60)

    url = f"{API_URL}/notas_servico/importar"
    params = {
        "data_inicial": data_inicial,
        "data_final": data_final
    }

    print(f"\nFazendo requisição POST para: {url}")
    print(f"Parâmetros: {params}")

    try:
        response = requests.post(url, params=params, timeout=60)

        print(f"\nStatus Code: {response.status_code}")
        print(f"\nResposta:")
        print("-" * 60)

        data = response.json()

        if data.get('success'):
            print("✓ SUCESSO!")
            print(f"\nPeríodo: {data['periodo']['data_inicial']} até {data['periodo']['data_final']}")
            print(f"Total encontradas: {data['total_encontradas']}")
            print(f"Total importadas: {data['total_importadas']}")
            print(f"Total atualizadas: {data['total_atualizadas']}")

            if data.get('erros'):
                print(f"\n⚠ Erros encontrados:")
                for erro in data['erros']:
                    print(f"  - NFSe {erro['nfse']}: {erro['erro']}")
        else:
            print("✗ ERRO!")
            print(f"Erro: {data.get('erro')}")
            print(f"Mensagem: {data.get('message')}")

        return response.status_code == 200 and data.get('success')

    except requests.exceptions.ConnectionError:
        print("✗ ERRO: Não foi possível conectar à API")
        print("Certifique-se de que a API está rodando!")
        return False
    except Exception as e:
        print(f"✗ ERRO: {e}")
        return False


def main():
    print("""
╔══════════════════════════════════════════════════════════╗
║     TESTE DE IMPORTAÇÃO DE NFSE - PREFEITURA DO RECIFE   ║
╚══════════════════════════════════════════════════════════╝
    """)

    # Teste 1: Importação padrão
    sucesso1 = testar_importacao_padrao()

    # Teste 2: Importação de ontem
    ontem = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    sucesso2 = testar_importacao_periodo(ontem, ontem)

    # Resumo
    print("\n" + "=" * 60)
    print("RESUMO DOS TESTES")
    print("=" * 60)
    print(f"Teste 1 (Padrão): {'✓ PASSOU' if sucesso1 else '✗ FALHOU'}")
    print(f"Teste 2 (Período): {'✓ PASSOU' if sucesso2 else '✗ FALHOU'}")
    print("=" * 60)

    if sucesso1 and sucesso2:
        print("\n🎉 Todos os testes passaram! API funcionando corretamente!")
    else:
        print("\n⚠ Alguns testes falharam. Verifique os erros acima.")


if __name__ == "__main__":
    main()
